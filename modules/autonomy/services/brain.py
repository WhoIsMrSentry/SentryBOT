import threading
import time
import logging
import random
import datetime
import json
import uuid
from typing import List, Optional

from .client import ServiceClient
from .idle_behaviors import IdleBehaviorPlanner
from .mood import MoodManager
from .memory import ShortTermMemory
from .affective_appraisal import AffectiveAppraisal
from .expression_director import ExpressionDirector
from .companion_rituals import CompanionRituals
from .proactive_planner import ProactivePlanner
from .barge_in import BargeInController
from .liveliness import LivelinessScheduler
from .interaction_feedback import InteractionFeedbackLearner
from .relationship_memory import RelationshipMemory
from .brain_parts.animations import AnimationSupportMixin
from .brain_parts.owner_guard import OwnerGuardMixin
from .brain_parts.responses import ResponseTagMixin
from .brain_parts.scenes import SceneMixin
from .brain_parts.timeline import TimelineMixin
from .brain_parts.vision import VisionMixin
from .brain_parts.vocal import VocalMixin

try:
    from modules.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None

# Agent Core integration
try:
    from modules.agent_core.services.agent import AgentOrchestrator  # type: ignore
    _AGENT_CORE_AVAILABLE = True
except ImportError:
    _AGENT_CORE_AVAILABLE = False

logger = logging.getLogger("autonomy")

_PAUSED_OPERATIONAL = frozenset({"sleep", "maintenance", "paused", "off", "shutdown", "resting"})


class AutonomyBrain(
    AnimationSupportMixin,
    TimelineMixin,
    OwnerGuardMixin,
    ResponseTagMixin,
    SceneMixin,
    VisionMixin,
    VocalMixin,
):
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None

        # Components
        self.mood = MoodManager(config)
        self.appraisal = AffectiveAppraisal(config)
        self.client = ServiceClient(config.get("endpoints", {}), config=config)
        self.expression = ExpressionDirector(self.client)
        self.idle_planner = IdleBehaviorPlanner(config)
        self.memory = ShortTermMemory(max_items=20)
        companion_cfg = config.get("companion", {}) if isinstance(config.get("companion", {}), dict) else {}
        self.relationship_memory = RelationshipMemory(
            enabled=bool(companion_cfg.get("enabled", True)),
            path=str(companion_cfg.get("relationship_memory_path", "modules/autonomy/data/relationship_memory.json")),
        )
        self.companion_rituals = CompanionRituals(
            companion_cfg.get("rituals", {}) if isinstance(companion_cfg.get("rituals", {}), dict) else {}
        )
        self.proactive_planner = ProactivePlanner(companion_cfg.get("proactive", {}) if isinstance(companion_cfg.get("proactive", {}), dict) else {})
        learning_cfg = companion_cfg.get("learning", {}) if isinstance(companion_cfg.get("learning", {}), dict) else {}
        self.feedback_learner = InteractionFeedbackLearner(learning_cfg.get("feedback", learning_cfg))
        self.barge_in = BargeInController(config.get("barge_in", {}) if isinstance(config.get("barge_in", {}), dict) else {})
        self.liveliness = LivelinessScheduler(config.get("liveliness", {}) if isinstance(config.get("liveliness", {}), dict) else {})
        self._vision_cfg = config.get("vision_hooks", {})
        self.owner_cfg = config.get("owner", {})

        # Agent Core (advanced reasoning, tool-calling, planning)
        self.agent = None
        if _AGENT_CORE_AVAILABLE:
            try:
                from modules.agent_core.config_loader import load_config as load_agent_core_config  # type: ignore

                agent_cfg = load_agent_core_config()
                self.agent = AgentOrchestrator(agent_cfg, autonomy_client=self.client)
                llm_cfg = agent_cfg.get("llm", {}) if isinstance(agent_cfg.get("llm", {}), dict) else {}
                provider = str(llm_cfg.get("provider", "ollama"))
                model = str(agent_cfg.get("agent", {}).get("model", ""))
                logger.info(
                    "Agent Core integrated successfully (provider=%s model=%s).",
                    provider,
                    model,
                )
            except Exception as exc:
                logger.warning("Agent Core init failed (non-fatal): %s", exc)

        # State
        self.state = {
            "last_interaction": time.time(),
            "is_bored": False,
            "is_sleeping": False,
            "last_speech_text": "",
            "last_speech_time": 0,
            "last_speech_language": "tr",
            "current_pan": 90,
            "current_tilt": 90,
            "last_emotion": None,
            "last_vision_poll": 0.0,
            "owner_last_seen": 0.0,
            "owner_lockout_until": 0.0,
            "owner_last_greet": 0.0,
            "rfid_authorized_until": 0.0,
            "last_speaker": None,
            "persona_mode": None,
        }
        self._people_last_seen = {}
        self._last_emotion_sent = None
        self._current_people = {}
        self._attempt_log = []
        self._owner_report_pending = False
        self._llm_rate_limit_until = 0.0
        self._last_owner_scan = 0.0
        self._last_idle_action = 0.0
        self._reset_daily_timeline()
        self._speech_req_lock = threading.Lock()
        self._active_speech_req_id: str = ""
        self._speech_busy: bool = False
        self._speech_min_interval_s = float(self.config.get("request_timeouts", {}).get("speech_min_interval_s", 0.8))
        visuals_cfg = self.config.get("visual_state", {}) if isinstance(self.config.get("visual_state", {}), dict) else {}
        self._visual_emotion_min_interval_s = float(visuals_cfg.get("emotion_min_interval_s", 2.0))
        self._visual_lock_default_s = float(visuals_cfg.get("default_lock_s", 2.2))
        self._visual_lock_strong_s = float(visuals_cfg.get("strong_lock_s", 4.5))
        self._visual_state_hold_s = float(visuals_cfg.get("state_hold_s", 3.0))
        self._visual_strong_emotions = {
            str(x).strip().lower()
            for x in (visuals_cfg.get("strong_emotions", ["fear", "angry", "furious"]) or [])
            if str(x).strip()
        }
        graph_cfg = visuals_cfg.get("transition_graph", {}) if isinstance(visuals_cfg.get("transition_graph", {}), dict) else {}
        self._visual_transition_graph = {
            str(src).strip().lower(): [
                str(dst).strip().lower()
                for dst in (targets if isinstance(targets, list) else [])
                if str(dst).strip()
            ]
            for src, targets in graph_cfg.items()
            if str(src).strip()
        }
        self._last_emotion_sync_ts: float = 0.0
        self._visual_lock_until: float = 0.0
        self._visual_lock_reason: str = ""
        self._visual_state_emotion: str = "neutral"
        self._visual_state_since: float = time.time()

    def start(self):
        if self.running:
            return
        self.running = True

        auto_select_persona = bool(self.config.get("llm", {}).get("auto_select_persona", False))
        if auto_select_persona:
            try:
                self.client.select_persona("sentry")
            except Exception:
                logger.warning("Failed to select persona 'sentry'")

        if bool(self.config.get("llm", {}).get("warmup_on_start", True)):
            try:
                self.client.warmup_ollama()
            except Exception:
                pass

        # Start Agent Core subsystems (sensors, idle behaviors, memory)
        if self.agent:
            try:
                self.agent.start()
            except Exception as exc:
                logger.warning("Agent Core start failed (non-fatal): %s", exc)

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("Autonomy Brain started.")

    def stop(self):
        self.running = False
        if self.agent:
            try:
                self.agent.stop()
            except Exception:
                pass
        if self.thread:
            self.thread.join()
        logger.info("Autonomy Brain stopped.")

    def _loop(self):
        interval = self.config.get("defaults", {}).get("loop_interval_ms", 1000) / 1000.0
        while self.running:
            try:
                self._sense()
                self._think()
            except Exception as exc:
                logger.error("Error in autonomy loop: %s", exc)
            time.sleep(interval)

    def interaction_occurred(self, source=None):
        """External ping that resets boredom timer and nudges mood."""
        self.state["last_interaction"] = time.time()
        self.state["is_bored"] = False
        if source and str(source).lower() != "api":
            self.state["last_speaker"] = source
        self.mood.modify("happiness", 1)

    def _sense(self):
        """Poll sensors for new information."""
        self._sense_sound_direction()
        self._sense_speech_text()
        self._sense_vision()

    def _sense_sound_direction(self):
        try:
            direction = self.client.get_speech_direction()
            angle = (direction or {}).get("angle") if isinstance(direction, dict) else None
            if isinstance(angle, (int, float)) and abs(angle) > 10:
                    self._react_to_sound(angle)
        except Exception:
            pass

    def _companion_paused(self) -> bool:
        if bool(self.state.get("is_sleeping")):
            return True
        try:
            op = self.client.get_operational_mode()
            return str(op).strip().lower() in _PAUSED_OPERATIONAL
        except Exception:
            return False

    def _sense_speech_text(self):
        if self._companion_paused():
            return
        try:
            speech = self.client.get_last_speech()
            if speech and speech.get("final") and speech.get("text"):
                text = speech["text"]
                lang = str(speech.get("language") or self.state.get("last_speech_language") or "tr")
                elapsed = time.time() - self.state["last_speech_time"]
                if text != self.state["last_speech_text"] and elapsed > self._speech_min_interval_s:
                    if self._speech_busy:
                        return
                    self.state["last_speech_text"] = text
                    self.state["last_speech_time"] = time.time()
                    self.state["last_speech_language"] = lang
                    threading.Thread(
                        target=self._react_to_speech,
                        args=(text,),
                        kwargs={"source_lang": lang},
                        daemon=True,
                    ).start()
        except Exception:
            pass

    def _sync_emotion(self):
        dominant = self.mood.get_dominant_emotion()
        now = time.time()
        if not dominant:
            return
        target_emotion = self._select_visual_emotion(dominant)
        if target_emotion == self._last_emotion_sent:
            return
        if (now - self._last_emotion_sync_ts) < self._visual_emotion_min_interval_s:
            return
        self._last_emotion_sent = target_emotion
        self._last_emotion_sync_ts = now
        self.state["last_emotion"] = target_emotion
        self.client.update_emotions([target_emotion])
        self.client.push_interaction_event(f"emotion:{target_emotion}")
        self._apply_emotion_visual_state(target_emotion)
        # Try to run a matching scene for the dominant emotion (e.g. emotion_joy)
        try:
            scene_name = self._emotion_scene_name(target_emotion)
            ran = self._run_scene(scene_name, context={"emotion": target_emotion})
            if ran:
                # emit a scene-level interaction event for other subsystems
                try:
                    self.client.push_interaction_event(f"scene.{scene_name}")
                except Exception:
                    pass
        except Exception:
            logger.debug("Failed to run emotion scene %s", scene_name, exc_info=True)

    _EMOTION_SCENE_ALIASES = {
        "sadness": "emotion_sad",
        "anger": "emotion_angry",
    }

    @classmethod
    def _emotion_scene_name(cls, emotion: str) -> str:
        key = str(emotion or "neutral").strip().lower()
        return cls._EMOTION_SCENE_ALIASES.get(key, f"emotion_{key}")

    def express(self, emotion: str, *, say: Optional[str] = None, language: Optional[str] = None) -> str:
        """Deliberately express an emotion across all modalities at once.

        Use for reactive, intentional expressions (greetings, reactions). Passive
        mood-driven visuals continue to flow through ``_sync_emotion``.
        """
        head = None
        try:
            profile = self.mood.get_body_language_profile() or {}
            pan = int(self.state.get("current_pan", 90)) + int(profile.get("pan_delta", 0))
            tilt = int(self.state.get("current_tilt", 90))
            head = (max(0, min(180, pan)), max(0, min(180, tilt)))
        except Exception:
            head = None
        return self.expression.express(emotion, say=say, language=language, move_head=head)

    def appraise_event(self, event: str, intensity: float = 1.0, *, emit: bool = True) -> Optional[str]:
        """Apply a causal emotion event to mood and announce it.

        Returns the matched event name (or ``None`` if the event is unknown).
        """
        matched = self.appraisal.apply(self.mood, event, intensity)
        if not matched:
            return None
        try:
            self.memory.add_event(f"Felt a reaction to: {matched}")
        except Exception:
            pass
        if emit:
            try:
                self.client.push_interaction_event(f"appraisal:{matched}")
            except Exception:
                pass
        return matched

    @staticmethod
    def _sentiment_event_for_text(text: str) -> Optional[str]:
        """Very lightweight keyword sentiment -> appraisal event mapping."""
        low = str(text or "").lower()
        if not low:
            return None
        rude = ("aptal", "salak", "gerizekal", "kapa cen", "sus ", "stupid", "shut up", "idiot")
        praise = ("aferin", "harikasin", "cok iyi", "tesekkur", "sevimlisin", "seviyorum", "good job", "well done", "thank you", "i love you")
        if any(tok in low for tok in rude):
            return "user_rude"
        if any(tok in low for tok in praise):
            return "user_praise"
        return None

    def _maybe_emit_speech_excited(self, text: str, sentiment_event: Optional[str]) -> None:
        """Emit autonomy.excited only when configured — not on every utterance."""
        cfg = self.config.get("speech_reactions", {}) if isinstance(self.config.get("speech_reactions"), dict) else {}
        if sentiment_event == "user_praise" and cfg.get("excited_on_praise", True):
            self.client.push_interaction_event("autonomy.excited")
            return
        if cfg.get("excited_on_speech", False):
            self.client.push_interaction_event("autonomy.excited")
            return
        if cfg.get("excited_on_questions", False):
            low = str(text or "").lower()
            if "?" in text or any(w in low for w in ("nedir", "nasıl", "what", "who", "how")):
                self.client.push_interaction_event("autonomy.excited")

    _EMOTION_COMMAND_PHRASES = (
        ("anger", ("sinirlen", "sinirli ol", "kizgin ol", "kızgın ol", "ofkeli ol", "öfkeli ol", "angry ol", "sinirli")),
        ("furious", ("cok sinirli", "çok sinirli", "delir", "cildir", "öfke", "ofke")),
        ("joy", ("mutlu ol", "sevin", "neselen", "neşelen", "gul", "gül")),
        ("sadness", ("uzul", "üzül", "mutsuz ol", "uzgun ol", "üzgün ol")),
        ("fear", ("kork", "korkut", "korkma")),
        ("surprise", ("sasir", "şaşır", "saskin", "şaşkın")),
        ("bored", ("sikil", "sıkıl", "sikildim", "sıkıldım")),
        ("tired", ("yorul", "uyu", "uykum var")),
        ("love", ("beni sev", "askim ol", "aşkım ol")),
        ("excitement", ("heyecanlan", "heyecanli ol", "heyecanlı ol")),
        ("confusion", ("kafan karisik", "kafan karışık", "anlamadim", "anlamadım")),
        ("worried", ("endiselen", "endişelen", "kaygilan")),
        ("curiosity", ("merak et", "merakli ol")),
    )

    @classmethod
    def _emotion_command_for_text(cls, text: str) -> Optional[str]:
        low = str(text or "").lower().strip()
        if not low:
            return None
        for canon, phrases in cls._EMOTION_COMMAND_PHRASES:
            if any(p in low for p in phrases):
                return canon
        try:
            from modules.common.emotion_vocab import get_vocab

            vocab = get_vocab()
            for token in low.replace(",", " ").split():
                key = token.strip("!.?")
                if len(key) < 4:
                    continue
                canon = vocab.canonical(key)
                if canon not in {"neutral", "curiosity"}:
                    return canon
        except Exception:
            pass
        return None

    @staticmethod
    def _emotion_command_reply(canon: str, lang: str) -> str:
        tr_replies = {
            "anger": "Tamam, sinirliyim! Ne istiyorsun?",
            "furious": "Çok sinirliyim! Dikkat et!",
            "joy": "Harika, mutluyum!",
            "sadness": "Tamam... biraz üzgünüm.",
            "fear": "Korkuyorum...",
            "surprise": "Vay! Şaşırdım!",
            "bored": "Sıkıldım galiba.",
            "tired": "Yorgunum...",
            "love": "Seni de seviyorum!",
            "excitement": "Heyecanlandım!",
            "confusion": "Kafam karıştı...",
            "worried": "Biraz endişeliyim.",
            "curiosity": "Merak ettim!",
            "neutral": "Tamam.",
        }
        en_replies = {
            "anger": "Fine, I'm angry! What do you want?",
            "furious": "I'm furious! Watch out!",
            "joy": "I'm happy!",
            "neutral": "Okay.",
        }
        replies = tr_replies if str(lang or "tr").startswith("tr") else en_replies
        return replies.get(str(canon or "neutral"), replies.get("neutral", "Okay."))

    def _handle_emotion_command(self, text: str, lang: str) -> bool:
        cmd = self._emotion_command_for_text(text)
        if not cmd:
            return False
        mood_axis = {
            "anger": "anger",
            "furious": "anger",
            "joy": "happiness",
            "fear": "fear",
            "sadness": "sadness",
            "excitement": "happiness",
            "love": "happiness",
        }
        axis = mood_axis.get(cmd)
        if axis:
            self.mood.modify(axis, 40)
        reply = self._emotion_command_reply(cmd, lang)
        canon = self.express(cmd, say=reply, language=lang)
        self.state["last_emotion"] = canon
        self.client.update_emotions([canon])
        visual = self._normalize_emotion_name(canon)
        try:
            self._run_scene(f"emotion_{visual}", context={"emotion": canon})
        except Exception:
            pass
        self.memory.add_event(f"User asked me to express: {cmd}")
        logger.info("Emotion command handled: %s -> %s", text, canon)
        return True

    def _think(self):
        now = time.time()
        self._ensure_timeline_day()
        self._refresh_rfid_authorization()

        if self._companion_paused() and not self.state.get("is_sleeping"):
            try:
                op = self.client.get_operational_mode()
                if str(op).strip().lower() in _PAUSED_OPERATIONAL:
                    self.state["is_sleeping"] = str(op).strip().lower() == "sleep"
            except Exception:
                pass

        self._check_sleep_cycle()
        if self.state["is_sleeping"]:
            if random.random() < 0.1:
                self.client.set_neopixel("breathe", emotions=["neutral"], duration=2.0)
            return

        self.mood.update()
        self._sync_emotion()
        self._liveliness_tick(now)

        if random.random() < 0.4:
            self._perform_micro_movement()

        self._maybe_scan_for_owner()
        self._forward_visual_events_to_agent()

        boredom_threshold = self.config.get("defaults", {}).get("boredom_threshold_s", 20)
        time_since_interaction = now - self.state["last_interaction"]
        if time_since_interaction > boredom_threshold:
            if not self.state["is_bored"]:
                logger.info("Robot is bored.")
                self.state["is_bored"] = True
                self.mood.modify("curiosity", 10)
                self.memory.add_event("I became bored because nothing happened for a while.")
            idle_cfg = self.config.get("behaviors", {}).get("idle_tree", {})
            idle_interval = float(idle_cfg.get("interval_s", 6.0))
            if now - self._last_idle_action >= idle_interval:
                if self._run_idle_behavior(now):
                    self._last_idle_action = now
                elif bool(idle_cfg.get("fallback_to_llm", True)) and random.random() < 0.2:
                    self._make_agentic_decision()
        else:
            self.state["is_bored"] = False

        self._run_companion_rituals(now)
        self._run_companion_proactive(now)

    def _run_companion_rituals(self, now: float) -> None:
        if self._speech_busy:
            return
        owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
        plan = self.companion_rituals.propose(
            now_ts=now,
            owner_present=owner_present,
            is_sleeping=bool(self.state.get("is_sleeping", False)),
        )
        if not plan:
            return
        text = str(plan.get("text", "")).strip()
        if not text:
            return
        emotion = str(plan.get("emotion", "joy")).strip()
        event = str(plan.get("event", "companion.ritual")).strip()
        self.client.push_interaction_event(event, {"text": text, "emotion": emotion})
        self._speak_with_mood(text, emotion=emotion)
        self.memory.add_event(f"Companion ritual: {text}")
        logger.info(
            "Companion ritual fired | event=%s emotion=%s text=%s",
            event,
            emotion,
            text,
        )

    def _run_companion_proactive(self, now: float) -> None:
        if self.state.get("is_sleeping"):
            return
        if self._speech_busy:
            return
        idle_s = max(0.0, now - float(self.state.get("last_interaction", now)))
        dominant = str(self.mood.get_dominant_emotion() or "neutral")
        speaker = str(self.state.get("last_speaker") or "")
        owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
        social_profile = self.relationship_memory.social_profile(speaker) if speaker else {}
        scene_ctx = {
            "summary": str(self.state.get("scene_summary", "") or ""),
            "importance": float(self.state.get("scene_importance", 0.0) or 0.0),
            "unspoken": bool(self.state.get("scene_unspoken", False)),
        }
        plan = self.proactive_planner.propose(
            now_ts=now,
            idle_s=idle_s,
            dominant_emotion=dominant,
            last_speaker=speaker,
            owner_present=owner_present,
            social_profile=social_profile,
            scene=scene_ctx,
        )
        if not plan:
            return
        text = str(plan.get("text", "")).strip()
        if not text:
            return
        if plan.get("scene_consumed"):
            self.state["scene_unspoken"] = False
        emotion = str(plan.get("emotion", "curiosity")).strip()
        event = str(plan.get("event", "companion.proactive")).strip()
        self.client.push_interaction_event(event, {"text": text, "emotion": emotion})
        self._speak_with_mood(text, emotion=emotion)
        self.memory.add_event(f"Proactive companion line: {text}")
        logger.info(
            "Companion proactive fired | event=%s emotion=%s text=%s",
            event,
            emotion,
            text,
        )

    def _forward_visual_events_to_agent(self) -> None:
        """Forward key autonomy/vision signals to Agent Core event endpoint."""
        if not hasattr(self.client, "emit_agent_event"):
            return
        try:
            ctx_resp = self.client.get_visual_context()
            if not (isinstance(ctx_resp, dict) and ctx_resp.get("available")):
                return
            ctx = ctx_resp.get("context", {}) if isinstance(ctx_resp.get("context", {}), dict) else {}
            hazards = ctx.get("hazards", []) if isinstance(ctx.get("hazards", []), list) else []
            people = ctx.get("people", []) if isinstance(ctx.get("people", []), list) else []
            if hazards:
                self.client.emit_agent_event("hazard_detected", {"count": len(hazards)})
                return
            owner_seen = False
            new_people = 0
            for p in people:
                if not isinstance(p, dict):
                    continue
                lvl = int(p.get("recognition_level", 0) or 0)
                rel = str(p.get("relationship", "")).lower()
                if lvl >= 5 or rel == "owner":
                    owner_seen = True
                if lvl <= 1:
                    new_people += 1
            if owner_seen:
                self.client.emit_agent_event("owner_follow_intent", {})
            elif new_people > 0:
                self.client.emit_agent_event("new_person_seen", {"count": new_people})
            elif self.state.get("is_bored"):
                self.client.emit_agent_event("idle_comment_request", {"prompt": "look around and comment naturally"})
        except Exception:
            pass

    def _run_idle_behavior(self, now: float) -> bool:
        choice = self.idle_planner.pick(now=now)
        if choice is None:
            return False
        logger.info("Idle behavior selected: %s", choice.name)
        self.idle_planner.stamp(choice.name, now=now)
        self.memory.add_event(f"Idle action: {choice.name}")
        self._execute_action(choice.name)
        return True

    def _make_agentic_decision(self):
        """Ask LLM what to do based on internal state using the native tool loop."""
        if not self.config.get("llm", {}).get("enabled", False):
            return

        events = "\n".join(self.memory.get_recent_events())
        social_context = self.relationship_memory.build_social_context(
            current_speaker=str(self.state.get("last_speaker") or "")
        )
        prompt = (
            f"You are currently BORED and IDLE.\n"
            f"Internal State:\n"
            f"- Happiness: {int(self.mood['happiness'])}/100, Energy: {int(self.mood['energy'])}/100, Curiosity: {int(self.mood['curiosity'])}/100\n"
            f"Recent Events:\n{events}\n\n"
            f"{social_context}\n\n"
            f"Use your internal physical tools right now (such as looking around, playing an animation on OLED, "
            f"or changing body lights) to entertain yourself or find something interesting to do. Do not ask for permission."
        )

        try:
            if self.agent:
                self.agent.memory.remember("agentic_decision", "I got bored so I decided to act on my own.")
                res = self.agent.step(prompt)
                if res and res.get("text"):
                    self._speak_with_mood(res["text"])
            else:
                logger.warning("Agent Core is disabled. Cannot make native decision.")
        except Exception as exc:
            logger.error("Agentic decision failed natively: %s", exc)

    def _execute_action(self, action):
        if action == "LOOK_AROUND":
            if self._visual_lock_active():
                logger.debug("Skipping LOOK_AROUND due to visual lock: %s", self._visual_lock_reason)
                return
            self.client.push_interaction_event("autonomy.look_around")
            self._emit_idle_visuals("look_around")
            if not self._trigger_animation("look_around"):
                self._head_scan_fallback()
        elif action == "BLINK":
            if self._visual_lock_active():
                return
            # Always emit a visual event so LED/OLED can react even if
            # servo animation endpoint reports success while degrading.
            self.client.push_interaction_event("autonomy.blink")
            self._emit_idle_visuals("blink")
            if not self._trigger_animation("blink"):
                self._blink_fallback()
        elif action == "SIGH":
            self._speak_with_mood("Hıııh.", emotion="tired")
            self.client.push_interaction_event("autonomy.bored")
            self._emit_idle_visuals("bored")
        elif action == "STRETCH":
            if self._visual_lock_active():
                return
            self.client.push_interaction_event("autonomy.stretch")
            self._emit_idle_visuals("stretch")
            if not self._trigger_animation("stretch"):
                self._stretch_fallback()
        elif action == "MONOLOGUE":
            self.client.push_interaction_event("autonomy.monologue")
            self._emit_idle_visuals("monologue")
            self._generate_monologue()

    def _emit_idle_visuals(self, action: str) -> None:
        """Direct best-effort LED/OLED hints for idle actions.

        Interactions engine remains primary route, but this keeps visible
        feedback alive when interactions adapter/config is degraded.
        """
        key = str(action or "").strip().lower()
        if self._visual_lock_active():
            return
        neo_map = {
            "blink": "RANDOM_BLINK",
            "look_around": "COMET",
            "stretch": "WAVE",
            "bored": "PULSE",
            "monologue": "TWINKLE",
        }
        oled_anim_map = {
            "blink": "blink",
            "look_around": "scanning",
            "monologue": "thinking",
        }
        oled_bitmap_map = {
            "stretch": "look_up",
            "bored": "bored",
        }

        try:
            effect = neo_map.get(key)
            if effect:
                self.client.set_neopixel(effect)
        except Exception:
            pass

        try:
            anim = oled_anim_map.get(key)
            if anim:
                self.client.oled_anim(anim)
                return
            bmp = oled_bitmap_map.get(key)
            if bmp:
                self.client.oled_show(bmp)
        except Exception:
            pass

    @staticmethod
    def _normalize_emotion_name(emotion: str) -> str:
        e = str(emotion or "neutral").strip().lower()
        aliases = {
            "sadness": "sad",
            "anger": "angry",
            "tire": "tired",
            "anxious": "fear",
        }
        return aliases.get(e, e or "neutral")

    def _select_visual_emotion(self, dominant_emotion: str) -> str:
        now = time.time()
        candidate = self._normalize_emotion_name(dominant_emotion)
        current = self._normalize_emotion_name(self._visual_state_emotion)
        strong = self._visual_strong_emotions
        if not current:
            self._visual_state_emotion = candidate
            self._visual_state_since = now
            return candidate
        if candidate == current:
            return current
        if candidate in strong:
            self._visual_state_emotion = candidate
            self._visual_state_since = now
            return candidate
        if (now - self._visual_state_since) < max(0.1, self._visual_state_hold_s):
            return current
        allowed = self._visual_transition_graph.get(current, [])
        if allowed and candidate not in allowed:
            return current
        self._visual_state_emotion = candidate
        self._visual_state_since = now
        return candidate

    def _visual_lock_active(self) -> bool:
        return time.time() < float(self._visual_lock_until)

    # Emotions that warrant a longer visual hold (high-arousal states).
    _STRONG_VISUAL_EMOTIONS = {"fear", "furious", "anger", "surprise"}

    def _apply_emotion_visual_state(self, emotion: str) -> None:
        e = str(emotion or "neutral").strip().lower()
        # Resolve eyes + LED effect + colour from the single canonical vocabulary
        # so every emotion (incl. anger/furious/surprise) gets coherent visuals.
        try:
            from modules.common.emotion_vocab import emotion_render

            render = emotion_render(e)
            canon = render.canonical
            effect = render.effect
            oled = render.oled
            color = list(render.rgb)
        except Exception:
            canon, effect, oled, color = "neutral", "BREATHE", "normal", [120, 120, 140]

        strong = canon in self._STRONG_VISUAL_EMOTIONS
        lock_s = self._visual_lock_strong_s if strong else self._visual_lock_default_s
        self._visual_lock_until = max(self._visual_lock_until, time.time() + max(0.2, float(lock_s)))
        self._visual_lock_reason = f"emotion:{canon}"
        try:
            self.client.set_neopixel(effect, emotions=[canon], color=color)
        except Exception:
            pass
        try:
            self.client.oled_show(oled)
        except Exception:
            pass

    def _react_to_sound(self, angle):
        """Turn head towards sound source."""
        logger.info("Sound detected at %s", angle)
        offset = max(-70, min(70, angle))
        target_pan = max(0, min(180, 90 + offset))
        self.state["current_pan"] = target_pan
        ran = self._run_scene(
            "curious_scan",
            context={"angle": int(angle), "target_pan": int(target_pan)},
        )
        if not ran:
            self.client.queue_action("head_move", priority=60, payload={"pan": target_pan, "tilt": self.state["current_tilt"]})
        self.client.push_interaction_event("autonomy.excited")
        self.state["last_interaction"] = time.time()
        self.mood.modify("curiosity", 5)
        self.mood.modify("energy", 2)
        self.memory.add_event(f"Heard sound at angle {angle}")

    def _barge_in_stop_speaking(self) -> None:
        """Stop robot TTS so the user can speak (wakeword barge-in)."""
        try:
            if self.agent and hasattr(self.agent, "speech_arbiter"):
                self.agent.speech_arbiter.interrupt_all()
            else:
                self.client.stop_speaking()
                self.client.interrupt_agent_speech()
        except Exception as exc:
            logger.debug("barge-in stop failed: %s", exc)

    def _robot_is_speaking(self) -> bool:
        """Best-effort check of whether TTS audio is currently playing."""
        try:
            if self.agent and hasattr(self.agent, "speech_arbiter"):
                return bool(self.agent.speech_arbiter.is_speaking())
        except Exception:
            pass
        try:
            status = self.client.get_speak_status()
            if isinstance(status, dict):
                return bool(status.get("speaking") or status.get("busy"))
        except Exception:
            pass
        return False

    def _react_to_speech(self, text, source_lang: str | None = None):
        """React to heard text."""
        from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

        low = str(text or "").lower()
        has_wake = contains_wakeword(low)
        # Natural barge-in: any meaningful utterance (not only a wakeword) cuts
        # off the robot if it's mid-sentence, like a real conversation.
        if self.barge_in.should_interrupt(
            robot_speaking=self._robot_is_speaking(),
            user_text=text,
            has_wakeword=has_wake,
        ):
            self._barge_in_stop_speaking()
        elif has_wake:
            self._barge_in_stop_speaking()

        request_id = uuid.uuid4().hex[:10]
        with self._speech_req_lock:
            self._active_speech_req_id = request_id
            self._speech_busy = True

        logger.info("Heard: %s", text)
        self.state["last_interaction"] = time.time()
        lang = str(source_lang or self.state.get("last_speech_language") or "tr")
        wake_only = len(strip_wakewords(low).split()) < 1 and contains_wakeword(low)
        if wake_only:
            self._run_scene("wakeword_reaction", context={"text": text})
            if len(strip_wakewords(low).split()) < 1:
                logger.info("Wakeword-only utterance; listening for command.")
                try:
                    self.client.start_speech_listening()
                except Exception:
                    pass
                with self._speech_req_lock:
                    if self._active_speech_req_id == request_id:
                        self._speech_busy = False
                return

        if self._handle_emotion_command(text, lang):
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False
            return

        self.mood.modify("happiness", 5)
        sentiment_event = self._sentiment_event_for_text(text)
        if sentiment_event:
            self.appraise_event(sentiment_event)
        self.memory.add_event(f"User said: {text}")
        self._log_conversation(text)
        speaker = self._guess_active_person()
        if speaker:
            self.state["last_speaker"] = speaker
            self._note_person_seen(speaker, emotion=str(self.state.get("last_emotion") or ""))
            self._remember_person_chat(speaker, text, role="user")
            if sentiment_event:
                self._apply_interaction_feedback(sentiment_event, speaker, text)

        self._maybe_emit_speech_excited(text, sentiment_event)

        blocked_response = self._maybe_block_request(text)
        if blocked_response:
            message, emotion = blocked_response
            self._speak_with_mood(message, emotion=emotion, language=lang)
            return

        if self._handle_owner_commands(text, speaker):
            return

        if self._features_locked_for_request(text):
            return

        if self._handle_follow_commands(text, speaker, lang):
            return

        is_question = "?" in text or any(
            key in text.lower() for key in ["nedir", "kimdir", "nasıl", "what", "who", "how"]
        )

        offline_cfg = self.config.get("offline_mode", {})
        if bool(offline_cfg.get("enabled", False)):
            target_service = "ollama"
            if not self.client.is_service_available(target_service):
                fallback = self._offline_reply(text, target_service)
                self.client.push_interaction_event("autonomy.offline", {"service": target_service})
                self._speak_with_mood(fallback, emotion="neutral", language=lang)
                self.memory.add_event(f"Offline fallback reply used for {target_service}: {fallback}")
                return

        response_text = ""
        response_actions = None
        raw_response = None
        try:
            # ── PRIMARY PATH: Agent Core (ReAct + Tool Calling + Safety) ──
            # Uses built-in ProgressManager + SpeechArbiter for staged
            # ack → progress → final lifecycle.  No manual _waiter thread
            # needed — agent.step() emits its own progress events.
            if self.agent:
                try:
                    # Wire SpeechArbiter speak_fn to autonomy's speak client
                    if not self.agent.speech_arbiter._speak_fn:
                        self.agent.speech_arbiter.set_speak_fn(
                            lambda text, tone=None, language=None: self.client.speak(
                                text, tone=tone, language=language or lang,
                            )
                        )

                    enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
                    agent_result = self.agent.step(enriched_text, language=lang, speaker=speaker)
                    if agent_result and agent_result.get("text"):
                        if not self._is_active_request(request_id):
                            return
                        response_text = agent_result["text"]
                        # Actions are already executed by the agent pipeline
                        # (validated -> safety filtered -> routed -> HAL)
                        logger.info("Agent Core handled speech with full pipeline.")
                        self.memory.add_event(f"Agent replied: {response_text}")
                        self._remember_person_chat(speaker, response_text, role="assistant")
                        tone = self._tone_profile(
                            self.state.get("last_emotion") or self.mood.get_dominant_emotion()
                        )
                        self.agent.speech_arbiter.enqueue_final(
                            response_text, language=lang, tone=tone,
                        )
                        return
                except Exception as exc:
                    logger.warning("Agent Core step failed, falling back to direct LLM: %s", exc)

            # ── FALLBACK PATH: Direct Ollama (no tool-calling) ──
            logger.info("Routing to Ollama...")
            enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
            resp = self.client.chat(
                enriched_text, source_lang=lang, response_lang=lang,
            )
            if resp and "answer" in resp:
                response_text = resp["answer"]
                response_actions = resp.get("actions")
                raw_response = resp.get("raw")
                trans = resp.get("translation") if isinstance(resp, dict) else None
                if isinstance(trans, dict) and trans.get("response_lang"):
                    lang = str(trans.get("response_lang"))

            if response_text:
                if not self._is_active_request(request_id):
                    return
                clean_text = self.apply_llm_response(response_text, response_actions, raw_response, speak=False)
                if clean_text:
                    if not self._is_active_request(request_id):
                        return
                    self._remember_person_chat(speaker, clean_text, role="assistant")
                    final_lang = lang
                    if detect_text_language:
                        final_lang = detect_text_language(clean_text, default=lang)
                    self._speak_with_mood(clean_text, language=final_lang)
                    logger.info("Reply: %s", clean_text)
                    self.memory.add_event(f"I replied: {clean_text}")
                else:
                    logger.info("LLM response only triggered physical actions.")
        except Exception as exc:
            logger.error("Failed to generate reply: %s", exc)
            # A failed reply both scares and frustrates the robot (causal appraisal).
            self.appraise_event("command_failed", emit=False)
            self.client.push_interaction_event("error", {"source": "ollama", "reason": "chat_failed"})
            self._apply_emotion_visual_state("fear")
        finally:
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False

    def _is_active_request(self, request_id: str) -> bool:
        with self._speech_req_lock:
            return self._active_speech_req_id == request_id

    def _apply_interaction_feedback(self, event: str, speaker: str, text: str) -> None:
        try:
            self.feedback_learner.apply(event, speaker, text=text)
        except Exception:
            pass

    def _remember_person_chat(self, speaker: str | None, text: str, role: str) -> None:
        person = str(speaker or "").strip()
        if not person or person.lower() == "unknown" or not text:
            return
        try:
            self.relationship_memory.add_chat(name=person, role=role, text=text)
        except Exception:
            pass
        try:
            self.client.append_person_chat(person=person, text=text, role=role)
        except Exception:
            pass

    def _enrich_user_text_with_companion_context(self, text: str, speaker: str | None) -> str:
        raw = str(text or "").strip()
        spk = str(speaker or "").strip()
        if not raw:
            return raw
        if not spk:
            return raw
        profile = self.relationship_memory.social_profile(spk)
        if not profile:
            return raw
        likes = profile.get("likes", []) if isinstance(profile.get("likes", []), list) else []
        topics = profile.get("topics", []) if isinstance(profile.get("topics", []), list) else []
        top_memory = str(profile.get("top_memory", "")).strip()
        hints = []
        trust = float(profile.get("trust_score", 0.0) or 0.0)
        if trust >= 0.7:
            hints.append("trust=high")
        elif trust <= 0.3:
            hints.append("trust=low")
        if likes:
            hints.append(f"likes={','.join([str(x) for x in likes[:3]])}")
        if topics:
            hints.append(f"topics={','.join([str(x) for x in topics[:3]])}")
        # Context-aware recall: surface the past snippet most relevant to what the
        # user is saying *now* (not just the highest-salience memory).
        recalled = ""
        try:
            from .recall import most_relevant

            candidates = self.relationship_memory.recall_candidates(spk)
            recalled = most_relevant(raw, candidates) or ""
        except Exception:
            recalled = ""
        if recalled:
            hints.append(f"recall={recalled[:90]}")
        elif top_memory:
            hints.append(f"memory={top_memory[:90]}")
        if not hints:
            return raw
        enriched = f"{raw}\n\n[CompanionContext speaker={spk}] {', '.join(hints)}"
        logger.info(
            "Companion context injected | speaker=%s hints=%s",
            spk,
            ", ".join(hints),
        )
        try:
            self.client.push_interaction_event("companion.context_injected", {"speaker": spk})
        except Exception:
            pass
        return enriched

    def _note_person_seen(self, name: str, emotion: str = "") -> None:
        person = str(name or "").strip()
        if not person or person.lower() == "unknown":
            return
        try:
            self.relationship_memory.observe_person(
                name=person,
                is_owner=bool(self._is_owner_name(person)) if hasattr(self, "_is_owner_name") else False,
                emotion=emotion,
            )
        except Exception:
            pass

    def _handle_follow_commands(self, text: str, speaker: str | None, language: str) -> bool:
        low = str(text or "").lower()
        stop_tokens = [
            "takibi bırak",
            "takibi birak",
            "beni takip etmeyi bırak",
            "beni takip etmeyi birak",
            "takipten çık",
            "takipten cik",
            "takibi durdur",
        ]
        start_tokens = [
            "beni takip et",
            "beni izle",
            "yüzümü takip et",
            "yuzumu takip et",
        ]

        if any(token in low for token in stop_tokens):
            result = self.client.stop_face_follow()
            ok = bool(isinstance(result, dict) and result.get("ok", False))
            message = "Yüz takibini durdurdum." if ok else "Yüz takibini şu an durduramıyorum."
            self._speak_with_mood(message, emotion="neutral", language=language)
            self.memory.add_event("Face follow stopped by voice command.")
            return True

        if any(token in low for token in start_tokens):
            target = None
            if speaker and str(speaker).strip() and str(speaker).strip().lower() != "unknown":
                target = str(speaker).strip()
            elif self.state.get("last_speaker") and str(self.state.get("last_speaker")).lower() != "unknown":
                target = str(self.state.get("last_speaker")).strip()

            result = self.client.start_face_follow(person=target)
            ok = bool(isinstance(result, dict) and result.get("ok", False))
            if ok:
                if target:
                    message = f"Tamam {target}, yüzünden takip modunu açtım."
                else:
                    message = "Yüz takibini açtım, seni kilitleyince takip edeceğim."
                self.memory.add_event(f"Face follow started. target={target or 'auto'}")
                self._speak_with_mood(message, emotion="joy", language=language)
            else:
                self._speak_with_mood("Yüz takibini şu an başlatamıyorum.", emotion="neutral", language=language)
            return True

        return False

    def _offline_reply(self, text: str, service: str) -> str:
        cfg = self.config.get("offline_mode", {})
        context = self._offline_context_label(text)
        contextual = cfg.get("contextual_replies", {}) if isinstance(cfg.get("contextual_replies", {}), dict) else {}
        ctx_pool = contextual.get(context)
        if isinstance(ctx_pool, list) and ctx_pool:
            return str(random.choice(ctx_pool))
        persona = cfg.get("persona_replies", {}) if isinstance(cfg.get("persona_replies", {}), dict) else {}
        mood_key = str(self.mood.get_dominant_emotion() or "neutral")
        mood_replies = persona.get(mood_key)
        if isinstance(mood_replies, list) and mood_replies:
            return str(random.choice(mood_replies))
        neutral_replies = persona.get("neutral")
        if isinstance(neutral_replies, list) and neutral_replies:
            return str(random.choice(neutral_replies))
        replies: List[str] = cfg.get("fallback_replies", []) if isinstance(cfg.get("fallback_replies", []), list) else []
        if replies:
            return str(random.choice(replies))
        if "?" in str(text):
            return "Su an baglanti yok, ama birazdan tekrar deneyebilirim."
        return f"Su an {service} ulasilamiyor, yine de buradayim."

    @staticmethod
    def _offline_context_label(text: str) -> str:
        t = str(text or "").strip().lower()
        if not t:
            return "generic"
        if "?" in t:
            return "question"
        if any(k in t for k in ["merhaba", "selam", "hey", "gunaydin", "iyi aksamlar"]):
            return "greeting"
        if any(k in t for k in ["yap", "ac", "kapat", "calistir", "dur", "git", "don"]):
            return "command"
        return "generic"

    def apply_llm_response(
        self,
        text: str,
        actions: dict | None = None,
        raw_text: str | None = None,
        speak: bool = False,
    ) -> str:
        """Harici modüllerin persona etiketlerini işletmesine izin ver."""
        clean = self._handle_llm_actions(text or "", actions, raw_text)
        if speak and clean:
            self._speak_with_mood(clean)
        return clean

    def update_palettes(self, palettes: dict[str, list[int]]) -> None:
        """Refresh in-memory palette cache after config edits."""
        defaults = self.config.setdefault("defaults", {})
        lights = defaults.setdefault("lights", {})
        lights["palettes"] = dict(palettes)

    def _check_sleep_cycle(self):
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled", False):
            return

        hour = datetime.datetime.now().hour
        start = sleep_cfg.get("start_hour", 23)
        end = sleep_cfg.get("end_hour", 7)

        if start > end:
            should_sleep = hour >= start or hour < end
        else:
            should_sleep = start <= hour < end

        if should_sleep and not self.state["is_sleeping"]:
            logger.info("Going to sleep...")
            self._deliver_timeline_summary()
            self.state["is_sleeping"] = True
            self.memory.add_event("Going to sleep now.")
            self.client.push_interaction_event("autonomy.sleep")
            ran = self._run_scene("sleepy_entry", context={"hour": hour})
            if not ran:
                self.client.queue_action("head_move", priority=70, payload={"pan": 90, "tilt": 120})
                self._speak_with_mood("İyi geceler.", emotion="tired")
            self.client.set_speech_tracking(False)

        elif not should_sleep and self.state["is_sleeping"]:
            logger.info("Waking up!")
            self.state["is_sleeping"] = False
            self.memory.add_event("Waking up from sleep.")
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            if not self._run_scene("wake_entry", context={"hour": hour}):
                self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)
