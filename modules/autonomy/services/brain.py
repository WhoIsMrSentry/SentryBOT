import threading
import time
import logging
import random
import datetime
import json
import uuid
from typing import Any, Dict, List, Optional

from .client import ServiceClient
from .idle_behaviors import IdleBehaviorPlanner
from .mood import MoodManager
from .memory import ShortTermMemory
from .affective_appraisal import AffectiveAppraisal
from .appraisal_triggers import speech_appraisal_event
from .expression_director import ExpressionDirector
from .companion_rituals import CompanionRituals
from .companion_lines import CompanionLineGenerator
from .proactive_planner import ProactivePlanner
from .barge_in import BargeInController
from .liveliness import LivelinessScheduler
from .interaction_feedback import InteractionFeedbackLearner
from .needs_engine import CompanionNeedsEngine
from .companion_goal_selector import CompanionGoalSelector
from .companion_goal_executor import CompanionGoalExecutor
from .companion_auto_execute_gate import CompanionAutoExecuteGate
from .companion_behavior_loop import CompanionBehaviorLoop
from .vision_context_needs_bridge import VisionContextNeedsBridge
from .audio_event_needs_bridge import AudioEventNeedsBridge
from .world_memory_rag import WorldMemoryRAG as WorldMemory
from .living_needs import LivingNeedsEngine
from .safe_navigation import SafeNavigationMemory
from .memory_decision_shadow import MemoryDecisionShadow
from .memory_needs_bias import MemoryNeedsBias
from .world_memory_autowriter import WorldMemoryAutoWriter
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
        lines_cfg = companion_cfg.get("lines", {}) if isinstance(companion_cfg.get("lines", {}), dict) else {}
        self.companion_lines = CompanionLineGenerator(self.client, lines_cfg)
        self.proactive_planner = ProactivePlanner(
            companion_cfg.get("proactive", {}) if isinstance(companion_cfg.get("proactive", {}), dict) else {},
            line_generator=self.companion_lines,
        )
        learning_cfg = companion_cfg.get("learning", {}) if isinstance(companion_cfg.get("learning", {}), dict) else {}
        self.feedback_learner = InteractionFeedbackLearner(learning_cfg.get("feedback", learning_cfg))
        needs_cfg = self.config.get("companion_needs", {}) if isinstance(self.config.get("companion_needs", {}), dict) else {}
        self.needs_engine = CompanionNeedsEngine(needs_cfg)
        goal_cfg = self.config.get("companion_goals", {}) if isinstance(self.config.get("companion_goals", {}), dict) else {}
        self.goal_selector = CompanionGoalSelector(goal_cfg)
        executor_cfg = self.config.get("companion_goal_executor", {}) if isinstance(self.config.get("companion_goal_executor", {}), dict) else {}
        self.goal_executor = CompanionGoalExecutor(executor_cfg, client=self.client)
        auto_exec_cfg = self.config.get("companion_auto_execute", {}) if isinstance(self.config.get("companion_auto_execute", {}), dict) else {}
        self.goal_auto_execute_gate = CompanionAutoExecuteGate(auto_exec_cfg)
        loop_cfg = self.config.get("companion_behavior_loop", {}) if isinstance(self.config.get("companion_behavior_loop", {}), dict) else {}
        self.companion_behavior_loop = CompanionBehaviorLoop(loop_cfg)
        vision_needs_cfg = self.config.get("vision_context_needs", {}) if isinstance(self.config.get("vision_context_needs", {}), dict) else {}
        self.vision_context_needs_bridge = VisionContextNeedsBridge(vision_needs_cfg)
        audio_needs_cfg = self.config.get("audio_event_needs", {}) if isinstance(self.config.get("audio_event_needs", {}), dict) else {}
        self.audio_event_needs_bridge = AudioEventNeedsBridge(audio_needs_cfg)
        world_memory_cfg = self.config.get("world_memory", {}) if isinstance(self.config.get("world_memory", {}), dict) else {}
        self.world_memory = WorldMemory(world_memory_cfg)
        living_needs_cfg = self.config.get("living_needs", {}) if isinstance(self.config.get("living_needs", {}), dict) else {}
        self.living_needs = LivingNeedsEngine(living_needs_cfg)
        safe_navigation_cfg = self.config.get("safe_navigation", {}) if isinstance(self.config.get("safe_navigation", {}), dict) else {}
        self.safe_navigation = SafeNavigationMemory(safe_navigation_cfg, client=self.client)
        memory_decision_cfg = self.config.get("memory_decision_shadow", {}) if isinstance(self.config.get("memory_decision_shadow", {}), dict) else {}
        self.memory_decision_shadow = MemoryDecisionShadow(memory_decision_cfg)
        memory_bias_cfg = self.config.get("memory_needs_bias", {}) if isinstance(self.config.get("memory_needs_bias", {}), dict) else {}
        self.memory_needs_bias = MemoryNeedsBias(memory_bias_cfg)
        world_memory_autowrite_cfg = self.config.get("world_memory_autowrite", {}) if isinstance(self.config.get("world_memory_autowrite", {}), dict) else {}
        self.world_memory_autowriter = WorldMemoryAutoWriter(world_memory_autowrite_cfg)
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
            "companion_needs": {},
            "companion_behavior_loop": {},
            "companion_behavior_history": [],
            "vision_context_needs": {},
            "vision_context_history": [],
            "audio_event_needs": {},
            "audio_event_history": [],
            "world_memory": {},
            "world_memory_history": [],
            "memory_decision_shadow": {},
            "memory_needs_bias": {},
            "world_memory_autowrite": {},
            "world_memory_autowrite_history": [],
            "living_needs": {},
            "living_needs_history": [],
            "safe_navigation": {},
            "sound_interrupt": {},
            "sound_interrupt_history": [],
        }
        self._people_last_seen = {}
        self._last_emotion_sent = None
        self._current_people = {}
        self._attempt_log = []
        self._owner_report_pending = False
        self._llm_rate_limit_until = 0.0
        self._last_owner_scan = 0.0
        self._last_idle_action = 0.0
        self._last_agentic_ts = 0.0
        self._last_alone_appraisal_ts = 0.0
        self._last_darkness_appraisal_ts = 0.0
        self._last_owner_left_appraisal_ts = 0.0
        self._owner_was_present = False
        self._owner_session_id: int | None = None
        self._reset_daily_timeline()
        self._speech_req_lock = threading.Lock()
        self._active_speech_req_id: str = ""
        self._speech_busy: bool = False
        self._speech_min_interval_s = float(self.config.get("request_timeouts", {}).get("speech_min_interval_s", 0.35))
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
        social_fill = float(
            self.config.get("defaults", {}).get("mood", {}).get("needs", {}).get("social", {}).get("interaction_fill", 18)
        )
        stim_drain = float(
            self.config.get("defaults", {}).get("mood", {}).get("needs", {}).get("stimulation", {}).get("interaction_drain", 12)
        )
        if hasattr(self.mood, "satisfy_need"):
            self.mood.satisfy_need("social", social_fill)
            self.mood.satisfy_need("stimulation", stim_drain)
        try:
            self.needs_engine.observe_interaction(str(source or "interaction"))
        except Exception:
            pass

    def _sense(self):
        """Poll sensors for new information."""
        self._sense_sound_direction()
        self._sense_speech_text()
        self._sense_vision()

    def _sense_sound_direction(self):
        cfg = self.config.get("sound_direction", {}) if isinstance(self.config.get("sound_direction", {}), dict) else {}
        interval = float(cfg.get("poll_interval_s", 2.0) or 2.0)
        now = time.time()
        if now - float(self.state.get("last_sound_direction_poll", 0.0) or 0.0) < max(0.2, interval):
            return
        self.state["last_sound_direction_poll"] = now
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

    def on_speech_final(self, text: str, language: str = "") -> bool:
        """Event-driven entry: speech module pushes final transcripts here.

        Removes the polling latency (loop interval + debounce) from the voice
        pipeline. The `_sense_speech_text` poll stays as a fallback and its
        dedup state is shared, so a pushed utterance is not handled twice.
        """
        text = str(text or "").strip()
        if not text or self._companion_paused():
            return False
        lang = str(language or self.state.get("last_speech_language") or "tr")
        return self._dispatch_final_speech(text, lang)

    def _dispatch_final_speech(self, text: str, lang: str) -> bool:
        elapsed = time.time() - self.state["last_speech_time"]
        if text == self.state["last_speech_text"] or elapsed <= self._speech_min_interval_s:
            return False
        if self._speech_busy:
            return False
        self.state["last_speech_text"] = text
        self.state["last_speech_time"] = time.time()
        self.state["last_speech_language"] = lang
        threading.Thread(
            target=self._react_to_speech,
            args=(text,),
            kwargs={"source_lang": lang},
            daemon=True,
        ).start()
        return True

    def _sense_speech_text(self):
        if self._companion_paused():
            return
        try:
            speech = self.client.get_last_speech()
            if speech and speech.get("final") and speech.get("text"):
                text = speech["text"]
                lang = str(speech.get("language") or self.state.get("last_speech_language") or "tr")
                self._dispatch_final_speech(text, lang)
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
        """Speech text -> appraisal event (praise, thanks, petted, …)."""
        return speech_appraisal_event(text)

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
        """Match only very short imperative emotion commands (1-2 words)."""
        low = str(text or "").lower().strip(" .!?")
        if not low:
            return None
        words = low.split()
        if len(words) > 2:
            return None
        for canon, phrases in cls._EMOTION_COMMAND_PHRASES:
            for phrase in phrases:
                p = phrase.strip().lower()
                if low == p or (len(words) == 1 and words[0] == p.split()[0]):
                    return canon
        if len(words) == 1:
            try:
                from modules.common.emotion_vocab import get_vocab

                canon = get_vocab().canonical(words[0])
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

        self._update_companion_needs(now)

        self._tick_companion_behavior_loop(now)

        if random.random() < 0.4:
            self._perform_micro_movement()

        self._maybe_scan_for_owner()
        self._check_owner_presence_appraisal(now)
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
                agentic_enabled = bool(idle_cfg.get("fallback_to_llm", True)) or bool(self.config.get("agentic", {}).get("enabled", True))
                if agentic_enabled and self._should_agentic_decision(now):
                    self._make_agentic_decision(reason="boredom")
                    self._last_agentic_ts = now
                    self._last_idle_action = now
                elif self._run_idle_behavior(now):
                    self._last_idle_action = now
        else:
            self.state["is_bored"] = False

        alone_threshold = float(self.config.get("defaults", {}).get("alone_threshold_s", 120))
        if time_since_interaction > alone_threshold and (now - self._last_alone_appraisal_ts) > alone_threshold:
            if self.appraise_event("alone_too_long", emit=True):
                self._last_alone_appraisal_ts = now

        self._run_companion_rituals(now)
        self._run_companion_proactive(now)

    def _update_companion_needs(self, now: float) -> None:
        try:
            owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
            owner_last_seen = float(self.state.get("owner_last_seen", 0.0) or 0.0)
            scene_ctx = {
                "summary": str(self.state.get("scene_summary", "") or ""),
                "importance": float(self.state.get("scene_importance", 0.0) or 0.0),
                "unspoken": bool(self.state.get("scene_unspoken", False)),
                "hazards": self.state.get("scene_hazards", []),
            }
            cfg_pc = self.config.get("pc_test", {}) if isinstance(self.config.get("pc_test", {}), dict) else {}
            pc_test = bool(cfg_pc.get("enabled", False))
            mood_state = getattr(self.mood, "state", {})
            mood_state = dict(mood_state) if isinstance(mood_state, dict) else {}
            needs_state = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
            needs_state = dict(needs_state) if isinstance(needs_state, dict) else {}
            if hasattr(self, "vision_context_needs_bridge"):
                try:
                    bridge_ctx = self.vision_context_needs_bridge.context(now=now)
                    self.state["vision_context_needs"] = bridge_ctx.get("status", bridge_ctx)
                    if bridge_ctx.get("available"):
                        scene_ctx.update(bridge_ctx.get("scene") or {})
                        if bridge_ctx.get("owner_present"):
                            owner_present = True
                        bridge_owner_ts = bridge_ctx.get("owner_last_seen_ts")
                        if bridge_owner_ts:
                            owner_last_seen = max(float(owner_last_seen or 0.0), float(bridge_owner_ts))
                        mood_state.update(bridge_ctx.get("mood_overrides") or {})
                        needs_state.update(bridge_ctx.get("needs_overrides") or {})
                except Exception as exc:
                    logger.debug("Vision context needs bridge failed: %s", exc)
            if hasattr(self, "audio_event_needs_bridge"):
                try:
                    audio_bridge_ctx = self.audio_event_needs_bridge.context(now=now)
                    self.state["audio_event_needs"] = audio_bridge_ctx.get("status", audio_bridge_ctx)
                    if audio_bridge_ctx.get("available"):
                        scene_ctx["audio_context"] = audio_bridge_ctx.get("audio_context") or {}
                        if audio_bridge_ctx.get("owner_present"):
                            owner_present = True
                        audio_owner_ts = audio_bridge_ctx.get("owner_last_heard_ts")
                        if audio_owner_ts:
                            owner_last_seen = max(float(owner_last_seen or 0.0), float(audio_owner_ts))
                        if audio_bridge_ctx.get("speech_busy"):
                            setattr(self, "_speech_busy", True)
                        mood_state.update(audio_bridge_ctx.get("mood_overrides") or {})
                        needs_state.update(audio_bridge_ctx.get("needs_overrides") or {})
                except Exception as exc:
                    logger.debug("Audio event needs bridge failed: %s", exc)
            snapshot = self.needs_engine.tick(
                now=now,
                last_interaction_ts=float(self.state.get("last_interaction", now) or now),
                mood_state=mood_state,
                needs_state=needs_state,
                owner_present=owner_present,
                owner_last_seen_ts=owner_last_seen or None,
                is_sleeping=bool(self.state.get("is_sleeping", False)),
                speech_busy=bool(getattr(self, "_speech_busy", False)),
                scene=scene_ctx,
                pc_test=pc_test,
            )
            snapshot = self._apply_memory_bias_to_needs(snapshot, now)
            self.state["companion_needs"] = snapshot
            goal_plan = self.goal_selector.select(
                snapshot,
                owner_present=owner_present,
                now=now,
            )
            self.state["companion_goal"] = goal_plan
            goal_event = str(goal_plan.get("event", "") or "").strip()
            if goal_event:
                self.client.push_interaction_event(goal_event, goal_plan)
            event = str(snapshot.get("event", "") or "").strip()
            if event:
                self.client.push_interaction_event(event, {
                    "dominant_need": snapshot.get("dominant_need"),
                    "recommended_goal": snapshot.get("recommended_goal"),
                    "scores": snapshot.get("scores", {}),
                    "confidence": snapshot.get("confidence", 0.0),
                })
        except Exception as exc:
            logger.debug("Companion needs update failed: %s", exc)

    def execute_companion_goal(self, payload: dict | None = None, **_: object) -> dict:
        try:
            plan = None
            if isinstance(payload, dict) and isinstance(payload.get("goal_plan"), dict):
                plan = payload.get("goal_plan")
            if not isinstance(plan, dict):
                plan = self.get_companion_goal_snapshot() if hasattr(self, "get_companion_goal_snapshot") else {}
            result = self.goal_executor.execute(plan)
            self.state["companion_goal_execution"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_vision_context_for_needs(self, payload: dict | None = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "vision_context_needs_bridge"):
                return {"ok": False, "available": False, "reason": "vision_context_bridge_missing"}
            result = self.vision_context_needs_bridge.observe(payload or {}, source=source)
            self.state["vision_context_needs"] = result
            history = list(self.state.get("vision_context_history") or [])
            history.append({
                "timestamp": result.get("timestamp"),
                "reason": result.get("reason"),
                "summary": result.get("summary", ""),
                "new_object": result.get("new_object", False),
                "owner_present": result.get("owner_present", False),
                "no_person": result.get("no_person", False),
                "hazards": result.get("hazards", []),
            })
            self.state["vision_context_history"] = history[-20:]
            try:
                result["memory_autowrite"] = self.observe_context_world_memory("vision", result)
            except Exception:
                pass
            try:
                self.client.push_interaction_event("vision.context", {
                    "reason": result.get("reason"),
                    "summary": result.get("summary", ""),
                    "new_object": result.get("new_object", False),
                    "owner_present": result.get("owner_present", False),
                    "no_person": result.get("no_person", False),
                })
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_audio_event_for_needs(self, payload: dict | None = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "audio_event_needs_bridge"):
                return {"ok": False, "available": False, "reason": "audio_event_bridge_missing"}
            result = self.audio_event_needs_bridge.observe(payload or {}, source=source)
            self.state["audio_event_needs"] = result
            history = list(self.state.get("audio_event_history") or [])
            history.append({
                "timestamp": result.get("timestamp"),
                "reason": result.get("reason"),
                "event_type": result.get("event_type", ""),
                "wakeword": result.get("wakeword", False),
                "speech": result.get("speech", False),
                "sound": result.get("sound", False),
                "silence": result.get("silence", False),
                "loud": result.get("loud", False),
            })
            self.state["audio_event_history"] = history[-20:]
            try:
                result["memory_autowrite"] = self.observe_context_world_memory("audio", result)
            except Exception:
                pass
            try:
                self.client.push_interaction_event("audio.context", {
                    "reason": result.get("reason"),
                    "event_type": result.get("event_type", ""),
                    "wakeword": result.get("wakeword", False),
                    "speech": result.get("speech", False),
                    "sound": result.get("sound", False),
                    "silence": result.get("silence", False),
                    "loud": result.get("loud", False),
                })
            except Exception:
                pass
            try:
                if result.get("sound") or result.get("wakeword") or result.get("speech") or result.get("loud"):
                    result["sound_interrupt"] = self.handle_sound_interrupt(result)
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_context_world_memory(self, source_type: str, context: dict | None = None) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            if not hasattr(self, "world_memory_autowriter"):
                return {"ok": False, "available": False, "reason": "world_memory_autowriter_missing"}
            payloads = self.world_memory_autowriter.build(source_type, context or {})
            results = []
            for payload in payloads:
                src = payload.get("source") if isinstance(payload, dict) else source_type
                results.append(self.world_memory.observe(payload, source=src or source_type))
            snapshot = {"ok": True, "available": True, "source_type": source_type, "count": len(results), "items": [r.get("item", {}) for r in results if isinstance(r, dict)], "created_count": sum(1 for r in results if isinstance(r, dict) and r.get("created"))}
            self.state["world_memory"] = self.world_memory.status()
            self.state["world_memory_autowrite"] = snapshot
            history = list(self.state.get("world_memory_autowrite_history") or [])
            history.append({"source_type": source_type, "count": snapshot.get("count", 0), "created_count": snapshot.get("created_count", 0), "items": [{"id": item.get("id"), "kind": item.get("kind"), "name": item.get("name")} for item in snapshot.get("items", []) if isinstance(item, dict)]})
            self.state["world_memory_autowrite_history"] = history[-50:]
            return snapshot
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc), "source_type": source_type}

    def get_world_memory_autowrite_snapshot(self) -> dict:
        try:
            current = self.state.get("world_memory_autowrite")
            if isinstance(current, dict) and current:
                data = dict(current)
            else:
                data = {"ok": True, "available": False, "reason": "never_written", "count": 0, "items": []}
            data["history"] = list(self.state.get("world_memory_autowrite_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def _apply_memory_bias_to_needs(self, snapshot: dict, now: float | None = None) -> dict:
        try:
            if not hasattr(self, "memory_needs_bias") or not hasattr(self, "memory_decision_shadow") or not hasattr(self, "world_memory"):
                return snapshot
            memory_snapshot = self.world_memory.status()
            recent_result = self.world_memory.recent(limit=25)
            recent = recent_result.get("items", []) if isinstance(recent_result, dict) else []
            shadow = self.memory_decision_shadow.evaluate(memory_snapshot, recent, now=now)
            self.state["memory_decision_shadow"] = shadow
            biased = self.memory_needs_bias.apply(snapshot, shadow, now=now)
            if isinstance(biased, dict):
                self.state["memory_needs_bias"] = biased.get("memory_bias", {})
                return biased
        except Exception as exc:
            try:
                self.state["memory_needs_bias"] = {"ok": False, "available": False, "error": str(exc)}
            except Exception:
                pass
        return snapshot

    def get_memory_needs_bias_snapshot(self) -> dict:
        try:
            if hasattr(self, "memory_needs_bias"):
                return self.memory_needs_bias.snapshot()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "memory_needs_bias_missing"}

    def evaluate_memory_needs_bias(self, payload: dict | None = None) -> dict:
        try:
            if not hasattr(self, "memory_needs_bias"):
                return {"ok": False, "available": False, "reason": "memory_needs_bias_missing"}
            data = payload if isinstance(payload, dict) else {}
            needs = data.get("needs") if isinstance(data.get("needs"), dict) else data.get("needs_snapshot")
            shadow = data.get("shadow") if isinstance(data.get("shadow"), dict) else data.get("memory_shadow")
            return self.memory_needs_bias.apply(needs if isinstance(needs, dict) else {}, shadow if isinstance(shadow, dict) else {}, now=data.get("now"))
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_memory_decision_shadow(self) -> dict:
        try:
            if not hasattr(self, "world_memory") or not hasattr(self, "memory_decision_shadow"):
                return {"ok": False, "available": False, "reason": "memory_decision_shadow_missing"}
            snapshot = self.world_memory.status()
            recent_result = self.world_memory.recent(limit=25)
            recent = recent_result.get("items", []) if isinstance(recent_result, dict) else []
            result = self.memory_decision_shadow.evaluate(snapshot, recent)
            self.state["memory_decision_shadow"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def evaluate_memory_decision_shadow(self, payload: dict | None = None) -> dict:
        try:
            if not hasattr(self, "memory_decision_shadow"):
                return {"ok": False, "available": False, "reason": "memory_decision_shadow_missing"}
            data = payload if isinstance(payload, dict) else {}
            snapshot = data.get("memory") if isinstance(data.get("memory"), dict) else data
            recent = data.get("recent") if isinstance(data.get("recent"), list) else None
            return self.memory_decision_shadow.evaluate(snapshot, recent, now=data.get("now"))
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_snapshot(self) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.status()
            self.state["world_memory"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_schema(self) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.schema()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_world_memory(self, payload: dict | None = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.observe(payload or {}, source=source)
            self.state["world_memory"] = self.world_memory.status()
            history = list(self.state.get("world_memory_history") or [])
            item = result.get("item") if isinstance(result, dict) else {}
            history.append({
                "timestamp": result.get("timestamp") if isinstance(result, dict) else None,
                "id": item.get("id") if isinstance(item, dict) else "",
                "kind": item.get("kind") if isinstance(item, dict) else "",
                "name": item.get("name") if isinstance(item, dict) else "",
                "created": result.get("created") if isinstance(result, dict) else False,
                "source": item.get("source") if isinstance(item, dict) else source,
            })
            self.state["world_memory_history"] = history[-50:]
            try:
                self.client.push_interaction_event("memory.observe", {
                    "kind": item.get("kind") if isinstance(item, dict) else "",
                    "name": item.get("name") if isinstance(item, dict) else "",
                    "created": result.get("created") if isinstance(result, dict) else False,
                })
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_recent(self, kind: str | None = None, limit: int = 10) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.recent(kind=kind or None, limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def recall_world_memory(self, query: str = "", limit: int = 8) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            if hasattr(self.world_memory, "recall"):
                return self.world_memory.recall(query or "", limit=limit)
            return self.world_memory.recent(limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_context(self, query: str = "", limit: int = 8) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing", "context": ""}
            if hasattr(self.world_memory, "build_context"):
                return self.world_memory.build_context(query or "", limit=limit)
            recent = self.world_memory.recent(limit=limit)
            items = recent.get("items", []) if isinstance(recent, dict) else []
            lines = [f"- {i.get('kind')}:{i.get('name')} | {i.get('summary')}" for i in items if isinstance(i, dict)]
            return {"ok": True, "available": True, "query": query or "", "context": "\n".join(lines), "items": items}
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc), "context": ""}

    def get_world_memory_history(self, limit: int = 20) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.history(limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def clear_world_memory(self, kind: str | None = None) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.clear(kind=kind or None)
            self.state["world_memory"] = self.world_memory.status()
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_audio_event_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("audio_event_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "audio_event_needs_bridge"):
                data = self.audio_event_needs_bridge.status()
            else:
                data = {"ok": False, "available": False, "reason": "audio_event_bridge_missing"}
            data["history"] = list(self.state.get("audio_event_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_vision_context_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("vision_context_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "vision_context_needs_bridge"):
                data = self.vision_context_needs_bridge.status()
            else:
                data = {"ok": False, "available": False, "reason": "vision_context_bridge_missing"}
            data["history"] = list(self.state.get("vision_context_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_companion_behavior_loop_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_behavior_loop")
            if isinstance(current, dict) and current:
                data = dict(current)
                data["available"] = True
                data["history"] = list(self.state.get("companion_behavior_history") or [])[-10:]
                return data
            if hasattr(self, "companion_behavior_loop"):
                status = self.companion_behavior_loop.status()
                status["available"] = False
                status["reason"] = "never_checked"
                status["history"] = []
                return status
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "behavior_loop_missing"}

    def tick_companion_behavior_loop(self, force: bool = False, **_: object) -> dict:
        try:
            now = time.time()
            needs = self.get_needs_snapshot() if hasattr(self, "get_needs_snapshot") else {}
            goal = self.get_companion_goal_snapshot() if hasattr(self, "get_companion_goal_snapshot") else {}
            decision = self.companion_behavior_loop.decide(
                needs=needs,
                goal=goal,
                now=now,
                sleeping=bool(self.state.get("is_sleeping", False)),
                speech_busy=bool(getattr(self, "_speech_busy", False)),
                force=force,
            )
            if not decision.get("should_tick"):
                self.state["companion_behavior_loop"] = decision
                return decision
            execution = self.tick_companion_auto_execute(force=force)
            result = self.companion_behavior_loop.mark_execution(decision, execution)
            self.state["companion_behavior_loop"] = result
            history = list(self.state.get("companion_behavior_history") or [])
            history.append({
                "timestamp": result.get("timestamp"),
                "dominant_need": result.get("dominant_need"),
                "behavior": result.get("behavior"),
                "reason": result.get("reason"),
                "executed": result.get("executed"),
                "execution_reason": result.get("execution_reason"),
            })
            self.state["companion_behavior_history"] = history[-20:]
            try:
                if result.get("executed"):
                    self.client.push_interaction_event("companion.behavior_loop", {
                        "dominant_need": result.get("dominant_need"),
                        "behavior": result.get("behavior"),
                                "reason": result.get("reason"),
                    })
            except Exception:
                pass
            return result
        except Exception as exc:
            result = {"ok": False, "available": False, "should_tick": False, "executed": False, "error": str(exc)}
            self.state["companion_behavior_loop"] = result
            return result

    def _tick_companion_behavior_loop(self, now: float) -> None:
        try:
            if hasattr(self, "companion_behavior_loop"):
                self.tick_companion_behavior_loop(force=False)
        except Exception as exc:
            logger.debug("Companion behavior loop tick failed: %s", exc)

    def get_companion_auto_execute_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_auto_execute")
            if isinstance(current, dict) and current:
                return dict(current)
            if hasattr(self, "goal_auto_execute_gate"):
                status = self.goal_auto_execute_gate.status()
                status["available"] = False
                status["reason"] = "never_checked"
                return status
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "auto_execute_gate_missing"}

    def tick_companion_auto_execute(self, payload: dict | None = None, force: bool = False, **_: object) -> dict:
        try:
            body = payload if isinstance(payload, dict) else {}
            plan = body.get("goal_plan") if isinstance(body.get("goal_plan"), dict) else None
            if not isinstance(plan, dict):
                plan = self.get_companion_goal_snapshot() if hasattr(self, "get_companion_goal_snapshot") else {}
            decision = self.goal_auto_execute_gate.decide(plan, force=force)
            if not decision.get("should_execute"):
                self.state["companion_auto_execute"] = decision
                return decision
            execution = self.execute_companion_goal({"goal_plan": plan})
            result = self.goal_auto_execute_gate.mark_execution(decision, execution)
            self.state["companion_auto_execute"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "should_execute": False, "executed": False, "error": str(exc)}

    def get_companion_goal_execution_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_goal_execution")
            if isinstance(current, dict) and current:
                return dict(current)
            if hasattr(self, "goal_executor"):
                status = self.goal_executor.status()
                status["available"] = False
                status["reason"] = "never_executed"
                return status
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "goal_executor_missing"}

    def get_companion_goal_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_goal")
            if isinstance(current, dict) and current:
                data = dict(current)
                data["available"] = True
                return data
            needs = self.get_needs_snapshot() if hasattr(self, "get_needs_snapshot") else {}
            plan = self.goal_selector.select(needs)
            plan["available"] = False
            plan["reason"] = "no_goal_snapshot_yet"
            return plan
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_needs_snapshot(self) -> dict:
        try:
            if hasattr(self, "living_needs") and bool(getattr(self.living_needs, "cfg", {}).get("enabled", True)):
                current = self.state.get("living_needs")
                if isinstance(current, dict) and current:
                    data = dict(current)
                    data["available"] = True
                    return data
                return self.tick_living_needs()
            if hasattr(self, "needs_engine"):
                current = self.state.get("companion_needs")
                if isinstance(current, dict) and current:
                    data = dict(current)
                    data["available"] = True
                    return data
                return self.needs_engine.snapshot()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "needs_engine_missing"}

    def tick_living_needs(self) -> dict:
        try:
            if not hasattr(self, "living_needs"):
                return {"ok": False, "available": False, "reason": "living_needs_missing"}
            now = time.time()
            vision = self._current_vision_snapshot()
            audio = self.state.get("audio_event_needs") if isinstance(self.state.get("audio_event_needs"), dict) else {}
            snapshot = self.living_needs.tick(now=now, state=self.state, mood=self.mood, vision=vision, audio=audio)
            snapshot = self._apply_memory_bias_to_needs(snapshot, now=now)
            self.state["living_needs"] = snapshot
            self.state["companion_needs"] = snapshot
            history = list(self.state.get("living_needs_history") or [])
            history.append({
                "timestamp": snapshot.get("timestamp"),
                "dominant_need": snapshot.get("dominant_need"),
                "recommended_goal": snapshot.get("recommended_goal"),
                "scores": snapshot.get("scores", {}),
            })
            self.state["living_needs_history"] = history[-50:]
            try:
                semantic = snapshot.get("semantic_state") if isinstance(snapshot.get("semantic_state"), dict) else {}
                self.client.set_expression_event("needs." + str(snapshot.get("dominant_need") or "balance"), {
                    "semantic_state": semantic,
                    "scores": snapshot.get("scores", {}),
                    "recommended_goal": snapshot.get("recommended_goal"),
                })
            except Exception:
                pass
            return snapshot
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["living_needs"] = result
            return result

    def get_living_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("living_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "living_needs"):
                data = self.living_needs.status()
            else:
                data = {"ok": False, "available": False, "reason": "living_needs_missing"}
            data["history"] = list(self.state.get("living_needs_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def _current_vision_snapshot(self) -> dict:
        out = {}
        try:
            tracks = self.client._get("camera", "/tracking/tracks", timeout_s=0.8)
            if isinstance(tracks, dict):
                out["tracks"] = tracks.get("tracks") if isinstance(tracks.get("tracks"), list) else tracks.get("items", [])
                out["target"] = tracks.get("target")
        except Exception:
            pass
        try:
            ctx = self.state.get("vision_context_needs")
            if isinstance(ctx, dict):
                out.update({k: v for k, v in ctx.items() if k not in out})
        except Exception:
            pass
        return out

    def execute_safe_rest_corner(self, payload: dict | None = None) -> dict:
        try:
            if not hasattr(self, "safe_navigation"):
                return {"ok": False, "available": False, "reason": "safe_navigation_missing"}
            result = self.safe_navigation.execute_rest_corner(payload or {})
            self.state["safe_navigation"] = result
            return result
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["safe_navigation"] = result
            return result

    def get_safe_navigation_status(self) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                return self.safe_navigation.status()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}

    def list_safe_places(self) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                return self.safe_navigation.list_places()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}

    def learn_safe_place(self, payload: dict | None = None) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                result = self.safe_navigation.learn_place(payload or {})
                try:
                    place = result.get("place") if isinstance(result, dict) else {}
                    if isinstance(place, dict):
                        self.observe_world_memory({
                            "kind": "place",
                            "name": place.get("name") or place.get("id"),
                            "summary": place.get("summary") or "learned safe place",
                            "confidence": place.get("safety_score", 0.6),
                            "salience": 0.65,
                            "tags": ["safe_place", "rest_place"],
                            "details": place,
                        }, source="safe_navigation")
                except Exception:
                    pass
                return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}

    def handle_sound_interrupt(self, payload: dict | None = None) -> dict:
        try:
            body = payload if isinstance(payload, dict) else {}
            event_type = str(body.get("event_type") or body.get("reason") or "sound").strip().lower()
            is_sound = bool(body.get("sound") or body.get("wakeword") or body.get("speech") or event_type in {"sound", "wakeword", "speech", "voice"})
            if not is_sound:
                return {"ok": True, "available": True, "handled": False, "reason": "not_sound_interrupt"}
            actions = []
            try:
                actions.append({"type": "expression", "result": self.client.set_expression_event("sound.interrupt", {"source": event_type, "payload": body})})
            except Exception as exc:
                actions.append({"type": "expression", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "liveliness", "result": self.client.set_liveliness(True, mode="alert", amplitude_deg=6, period_ms=1800)})
            except Exception as exc:
                actions.append({"type": "liveliness", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "head", "result": self.client.move_head(90, 86)})
            except Exception as exc:
                actions.append({"type": "head", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "camera_target", "result": self.client._post("camera", "/tracking/select", {"label": "person", "strategy": "center"}, timeout_s=1.0)})
            except Exception as exc:
                actions.append({"type": "camera_target", "ok": False, "error": str(exc)})
            try:
                self.observe_world_memory({
                    "kind": "episode",
                    "name": "sound_interrupt",
                    "summary": "Sound interrupted resting or idle behavior; robot woke and looked for the source.",
                    "confidence": 0.7,
                    "salience": 0.7,
                    "tags": ["sound", "interrupt", "wake"],
                    "details": body,
                }, source="audio_interrupt")
            except Exception:
                pass
            result = {"ok": True, "available": True, "handled": True, "timestamp": time.time(), "event_type": event_type, "actions": actions}
            self.state["sound_interrupt"] = result
            hist = list(self.state.get("sound_interrupt_history") or [])
            hist.append({"timestamp": result["timestamp"], "event_type": event_type, "handled": True})
            self.state["sound_interrupt_history"] = hist[-20:]
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "handled": False, "error": str(exc)}

    def get_sound_interrupt_snapshot(self) -> dict:
        data = self.state.get("sound_interrupt") if isinstance(self.state.get("sound_interrupt"), dict) else {}
        if not data:
            data = {"ok": True, "available": False, "reason": "never_interrupted"}
        out = dict(data)
        out["history"] = list(self.state.get("sound_interrupt_history") or [])[-10:]
        return out

    def _run_companion_rituals(self, now: float) -> None:
        if self._speech_busy:
            return
        owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
        plan = self.companion_rituals.propose(
            now_ts=now,
            owner_present=owner_present,
            is_sleeping=bool(self.state.get("is_sleeping", False)),
            line_generator=self.companion_lines,
            needs=self.mood.get_needs() if hasattr(self.mood, "get_needs") else {},
            dominant_emotion=str(self.mood.get_dominant_emotion() or "neutral"),
            absence_s=max(0.0, self._owner_absence_seconds(now)),
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
            needs=self.mood.get_needs() if hasattr(self.mood, "get_needs") else {},
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
        """Forward key autonomy/vision signals to Agent Core event endpoint and trigger LLM reactions."""
        interval = float(self._vision_cfg.get("forward_interval_s", 8.0) or 8.0)
        now = time.time()
        if now - float(self.state.get("last_agent_vision_forward_poll", 0.0) or 0.0) < max(1.0, interval):
            return
        self.state["last_agent_vision_forward_poll"] = now
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
                self.appraise_event("loud_noise", intensity=min(1.0, len(hazards) / 3.0))
                # LLM reaction to hazard
                if self.agent and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: Visual hazard detected! {len(hazards)} hazard(s) in view. "
                            f"React appropriately - express alarm, move to safety, or investigate. "
                            f"Use your tools (like express_emotion) to act, then confirm briefly."
                        )
                        self.agent.step_event("hazard_detected", prompt)
                    except Exception as exc:
                        logger.debug("Hazard event step_event failed: %s", exc)
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
                # LLM reaction to owner
                if self.agent and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: Your owner just appeared in view! "
                            f"Express joy/excitement. Greet them naturally, move your head toward them, "
                            f"maybe say something warm. Use your tools (like express_emotion) to act, then confirm briefly."
                        )
                        self.agent.step_event("owner_seen", prompt)
                    except Exception as exc:
                        logger.debug("Owner seen event step_event failed: %s", exc)
            elif new_people > 0:
                self.client.emit_agent_event("new_person_seen", {"count": new_people})
                self.appraise_event("new_person", intensity=min(1.0, new_people / 2.0))
                # LLM reaction to stranger
                if self.agent and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: You see {new_people} new person/people you don't recognize. "
                            f"React with curiosity or caution. Turn toward them, maybe say hello or observe silently. "
                            f"Use your tools (like express_emotion) to express your reaction, then confirm in one sentence."
                        )
                        self.agent.step_event("new_person_seen", prompt)
                    except Exception as exc:
                        logger.debug("New person event step_event failed: %s", exc)
            elif self.state.get("vision_context_needs", {}).get("new_object"):
                self.appraise_event("new_object", intensity=0.5)
                self.client.emit_agent_event("new_object_seen", {})
                if self.agent and self.config.get("llm", {}).get("enabled", False):
                    try:
                        self._make_agentic_decision(reason="vision", context_note="I see a new object that I haven't seen before. I should investigate it.")
                    except Exception as exc:
                        logger.debug("New object agentic decision failed: %s", exc)
            elif self.state.get("is_bored"):
                self.client.emit_agent_event("idle_comment_request", {"prompt": "look around and comment naturally"})
                # LLM idle comment
                if self.agent and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: You're bored and nothing's happening. Look around the room and make a "
                            f"spontaneous comment or observation. Pick something interesting to look at, "
                            f"express a brief thought. Use your tools (like express_emotion), then speak naturally."
                        )
                        self.agent.step_event("idle_comment", prompt)
                    except Exception as exc:
                        logger.debug("Idle comment event step_event failed: %s", exc)
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

    def _check_owner_presence_appraisal(self, now: float) -> None:
        if not self.owner_cfg.get("enabled"):
            return
        present = self._owner_seen_recently()
        self._sync_owner_session(present)
        if self._owner_was_present and not present:
            last = float(self.state.get("owner_last_seen", 0.0) or 0.0)
            timeout = float(self.owner_cfg.get("presence_timeout_s", 30))
            if last > 0 and (now - last) >= timeout:
                if (now - self._last_owner_left_appraisal_ts) >= max(60.0, timeout):
                    self.appraise_event("owner_left")
                    self._last_owner_left_appraisal_ts = now
        self._owner_was_present = present

    def _owner_sessions_cfg(self) -> Dict[str, Any]:
        companion = self.config.get("companion", {}) if isinstance(self.config.get("companion"), dict) else {}
        cfg = companion.get("owner_sessions", {})
        return cfg if isinstance(cfg, dict) else {}

    def _social_db(self):
        return getattr(self.mood, "_social_db", None)

    def _sync_owner_session(self, owner_present: bool) -> None:
        cfg = self._owner_sessions_cfg()
        if not cfg.get("enabled", True):
            return
        db = self._social_db()
        if db is None:
            return
        source = str(cfg.get("source", "vision") or "vision")
        try:
            if owner_present:
                active = db.owner_sessions.active()
                if active is None:
                    self._owner_session_id = int(db.owner_sessions.start(source=source))
                else:
                    self._owner_session_id = int(active.get("id") or 0) or None
            elif self._owner_session_id is not None:
                db.owner_sessions.end(self._owner_session_id)
                self._owner_session_id = None
            elif db.owner_sessions.active() is not None:
                db.owner_sessions.end_active()
        except Exception as exc:
            logger.debug("owner session sync failed: %s", exc)

    def _owner_absence_seconds(self, now: float) -> float:
        db = self._social_db()
        if db is not None:
            try:
                rows = db.owner_sessions.recent(limit=2)
                for row in rows:
                    end_ts = row.get("end_ts")
                    if end_ts:
                        return max(0.0, now - float(end_ts))
            except Exception:
                pass
        last = float(self.state.get("owner_last_seen", 0.0) or 0.0)
        if last > 0:
            return max(0.0, now - last)
        return 0.0

    def _preference_summary(self, speaker: str = "") -> str:
        spk = str(speaker or self.state.get("last_speaker") or "").strip()
        if not spk:
            return ""
        profile = self.relationship_memory.social_profile(spk)
        if not profile:
            return ""
        likes = profile.get("likes", []) if isinstance(profile.get("likes"), list) else []
        dislikes = profile.get("dislikes", []) if isinstance(profile.get("dislikes"), list) else []
        topics = profile.get("topics", []) if isinstance(profile.get("topics"), list) else []
        parts = []
        if likes:
            parts.append(f"likes={','.join(str(x) for x in likes[:3])}")
        if dislikes:
            parts.append(f"dislikes={','.join(str(x) for x in dislikes[:2])}")
        if topics:
            parts.append(f"topics={','.join(str(x) for x in topics[:3])}")
        trust = float(profile.get("trust_score", 0.0) or 0.0)
        parts.append(f"trust={trust:.2f}")
        return "; ".join(parts)

    def _recent_companion_activity_summary(self, limit: int = 4) -> str:
        db = self._social_db()
        if db is None:
            return ""
        try:
            rows = db.interaction_events.recent(limit=limit)
        except Exception:
            return ""
        bits = []
        for row in rows:
            kind = str(row.get("kind") or "").strip()
            if kind.startswith(("companion.", "appraisal:", "autonomy.")):
                bits.append(kind)
        return ", ".join(bits[:limit])

    def _check_darkness_appraisal(self, now: float) -> None:
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled"):
            return
        hour = datetime.datetime.now().hour
        start = int(sleep_cfg.get("start_hour", 23))
        end = int(sleep_cfg.get("end_hour", 7))
        if start > end:
            dark = hour >= start or hour < end
        else:
            dark = start <= hour < end
        if not dark:
            return
        if (now - self._last_darkness_appraisal_ts) < 300:
            return
        if self.appraise_event("darkness", emit=False):
            self._last_darkness_appraisal_ts = now

    def _should_agentic_decision(self, now: float) -> bool:
        cfg = self.config.get("agentic", {}) if isinstance(self.config.get("agentic"), dict) else {}
        if not cfg.get("enabled", True):
            return False
        min_interval = float(cfg.get("min_interval_s", 45.0))
        if now - self._last_agentic_ts < min_interval:
            return False
        triggers = cfg.get("triggers", {}) if isinstance(cfg.get("triggers"), dict) else {}
        needs = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
        if float(needs.get("social", 0)) >= float(triggers.get("social_need", 72)):
            return True
        if float(needs.get("stimulation", 0)) >= float(triggers.get("stimulation_need", 68)):
            return True
        if float(self.mood.get("energy", 100) or 100) <= float(triggers.get("low_energy", 25)):
            return True
        if float(needs.get("rest", 100)) <= float(triggers.get("low_rest", 22)):
            return True
        return random.random() < float(cfg.get("fallback_random_chance", 0.12))

    def _mood_trend_summary(self) -> str:
        db = getattr(self.mood, "_social_db", None)
        if db is None:
            return ""
        try:
            rows = db.mood_snapshots.recent(limit=5)
            if len(rows) < 2:
                return ""
            latest = rows[0]
            oldest = rows[-1]
            dh = float(latest.get("happiness", 0)) - float(oldest.get("happiness", 0))
            de = float(latest.get("energy", 0)) - float(oldest.get("energy", 0))
            return f"mood_trend happiness {dh:+.0f}, energy {de:+.0f} over {len(rows)} snapshots"
        except Exception:
            return ""

    def _last_sighting_summary(self, speaker: str = "") -> str:
        db = getattr(self.mood, "_social_db", None)
        if db is None:
            return ""
        try:
            rows = db.sightings.recent(limit=3)
            if not rows:
                return ""
            last = rows[0]
            ago = int(max(0, time.time() - float(last.get("ts", 0))))
            return f"last sighting {ago}s ago (person_id={last.get('person_id', '?')})"
        except Exception:
            return ""

    def _make_agentic_decision(self, reason: str = "boredom", context_note: str = ""):
        """Ask LLM what to do based on internal state and trigger reason."""
        if not self.config.get("llm", {}).get("enabled", False):
            return

        events = "\n".join(self.memory.get_recent_events())
        social_context = self.relationship_memory.build_social_context(
            current_speaker=str(self.state.get("last_speaker") or "")
        )
        pref_summary = self._preference_summary()
        activity = self._recent_companion_activity_summary()
        needs = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
        mood_trend = self._mood_trend_summary()
        sighting = self._last_sighting_summary(str(self.state.get("last_speaker") or ""))
        
        situation = f"You are currently IDLE with unmet needs."
        if reason == "vision":
            situation = f"You just noticed something visually: {context_note}"
        elif reason == "audio":
            situation = f"You just heard something: {context_note}"
        elif reason == "social":
            situation = f"Social context update: {context_note}"
        elif reason == "memory":
            situation = f"You just remembered something: {context_note}"

        prompt = (
            f"{situation}\n"
            f"Internal State:\n"
            f"- Happiness: {int(self.mood['happiness'])}/100, Energy: {int(self.mood['energy'])}/100, "
            f"Curiosity: {int(self.mood['curiosity'])}/100\n"
            f"- Needs: social={needs.get('social', 0)}, stimulation={needs.get('stimulation', 0)}, "
            f"rest={needs.get('rest', 0)}\n"
            f"Recent Events:\n{events}\n\n"
            f"{social_context}\n"
            f"{('Preferences: ' + pref_summary) if pref_summary else ''}\n"
            f"{('Recent activity: ' + activity) if activity else ''}\n"
            f"{mood_trend}\n{sighting}\n\n"
            f"Use your internal physical tools right now (such as looking around, playing an animation on OLED, "
            f"or changing body lights) to react to this situation, entertain yourself, or find something interesting to do. Do not ask for permission."
        )

        try:
            if self.agent:
                self.agent.memory.remember("agentic_decision", "I got bored so I decided to act on my own.")
                res = self.agent.step(prompt)
                if res and res.get("text"):
                    self._speak_with_mood(res["text"])
                    self.appraise_event("command_ok", emit=False)
            else:
                logger.warning("Agent Core is disabled. Cannot make native decision.")
        except Exception as exc:
            logger.error("Agentic decision failed natively: %s", exc)
            self.appraise_event("command_failed", emit=False)

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
        """Turn head towards sound source and trigger LLM reaction."""
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

        # LLM-driven reaction to sound
        if self.agent and self.config.get("llm", {}).get("enabled", False):
            try:
                prompt = (
                    f"You just heard a sudden sound from angle {int(angle)} degrees. "
                    f"Your head turned toward it (pan={int(target_pan)}). "
                    f"React naturally - express curiosity, surprise, or caution. "
                    f"Use your physical tools (express_emotion, move_head, look_around, speak). "
                    f"Do not ask for permission."
                )
                self.agent.step_event("sound_detected", prompt, trace_id=f"sound_{int(time.time())}")
            except Exception as exc:
                logger.debug("Sound event step_event failed: %s", exc)

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

    def _handle_barge_in_and_wakeword(self, text: str, low: str, has_wake: bool, request_id: str) -> bool:
        from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

        if self.barge_in.should_interrupt(robot_speaking=self._robot_is_speaking(), user_text=text, has_wakeword=has_wake):
            self._barge_in_stop_speaking()
        elif has_wake:
            self._barge_in_stop_speaking()

        if contains_wakeword(low) and len(strip_wakewords(low).split()) < 1:
            self._run_scene("wakeword_reaction", context={"text": text})
            logger.info("Wakeword-only utterance; listening for command.")
            try:
                self.client.start_speech_listening()
            except Exception:
                pass
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False
            return True
        return False

    def _handle_speech_command_shortcuts(self, text: str, lang: str, request_id: str) -> bool:
        companion_cfg = self.config.get("companion", {}) if isinstance(self.config.get("companion"), dict) else {}
        if companion_cfg.get("voice_ai_tools", True) and self.agent:
            return False
        if not companion_cfg.get("emotion_command_shortcut", False):
            return False
        if self._handle_emotion_command(text, lang):
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False
            return True
        return False

    def _process_speech_social_context(self, text: str) -> str | None:
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
        return speaker

    def _handle_blocked_or_special_commands(self, text: str, speaker: str | None, lang: str) -> bool:
        blocked_response = self._maybe_block_request(text)
        if blocked_response:
            message, emotion = blocked_response
            self._speak_with_mood(message, emotion=emotion, language=lang)
            return True
        if self._handle_owner_commands(text, speaker):
            return True
        if self._features_locked_for_request(text):
            return True
        if self._handle_follow_commands(text, speaker, lang):
            return True
        return False

    def _handle_offline_mode(self, text: str, lang: str) -> bool:
        offline_cfg = self.config.get("offline_mode", {})
        if not bool(offline_cfg.get("enabled", False)):
            return False
        target_service = "ollama"
        if not self.client.is_service_available(target_service):
            fallback = self._offline_reply(text, target_service)
            self.client.push_interaction_event("autonomy.offline", {"service": target_service})
            self._speak_with_mood(fallback, emotion="neutral", language=lang)
            self.memory.add_event(f"Offline fallback reply used for {target_service}: {fallback}")
            return True
        return False

    def _try_agent_core_path(self, text: str, lang: str, speaker: str | None, request_id: str) -> bool:
        if not self.agent:
            return False
        try:
            if not self.agent.speech_arbiter._speak_fn:
                self.agent.speech_arbiter.set_speak_fn(
                    lambda text, tone=None, language=None, trace_id=None: self.client.speak_preferred(
                        text,
                        tone=tone,
                        language=language or lang,
                        trace_id=trace_id,
                    )
                )
            enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
            agent_result = self.agent.step(
                enriched_text,
                language=lang,
                speaker=speaker,
                native_tools=True,
                trace_id=request_id,
            )
            if agent_result and agent_result.get("text"):
                if not self._is_active_request(request_id):
                    return True
                logger.info("Agent Core handled speech with full pipeline.")
                self.memory.add_event(f"Agent replied: {agent_result['text']}")
                self._remember_person_chat(speaker, agent_result["text"], role="assistant")
                if not agent_result.get("speech_handled"):
                    tone = self._tone_profile(self.state.get("last_emotion") or self.mood.get_dominant_emotion())
                    self.agent.speech_arbiter.enqueue_final(
                        agent_result["text"],
                        language=lang,
                        tone=tone,
                        trace_id=request_id,
                    )
                return True
        except Exception as exc:
            logger.warning("Agent Core step failed, falling back to direct LLM: %s", exc)
        return False

    def _try_direct_llm_path(self, text: str, lang: str, speaker: str | None, request_id: str) -> None:
        logger.info("Routing to Ollama...")
        enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
        resp = self.client.chat(enriched_text, source_lang=lang, response_lang=lang)
        response_text = ""
        response_actions = None
        raw_response = None
        if resp and "answer" in resp:
            response_text = resp["answer"]
            response_actions = resp.get("actions")
            raw_response = resp.get("raw")
            trans = resp.get("translation") if isinstance(resp, dict) else None
            if isinstance(trans, dict) and trans.get("response_lang"):
                lang = str(trans.get("response_lang"))

        if not response_text:
            return
        if not self._is_active_request(request_id):
            return
        clean_text = self.apply_llm_response(response_text, response_actions, raw_response, speak=False)
        if not clean_text:
            logger.info("LLM response only triggered physical actions.")
            return
        if not self._is_active_request(request_id):
            return
        self._remember_person_chat(speaker, clean_text, role="assistant")
        final_lang = lang
        if detect_text_language:
            final_lang = detect_text_language(clean_text, default=lang)
        self._speak_with_mood(clean_text, language=final_lang)
        logger.info("Reply: %s", clean_text)
        self.memory.add_event(f"I replied: {clean_text}")

    def _react_to_speech(self, text, source_lang: str | None = None):
        """React to heard text."""
        from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

        low = str(text or "").lower()
        has_wake = contains_wakeword(low)

        request_id = uuid.uuid4().hex[:10]
        with self._speech_req_lock:
            self._active_speech_req_id = request_id
            self._speech_busy = True

        logger.info("Heard: %s", text)
        self.state["last_interaction"] = time.time()
        lang = str(source_lang or self.state.get("last_speech_language") or "tr")

        if self._handle_barge_in_and_wakeword(text, low, has_wake, request_id):
            return

        if self._handle_speech_command_shortcuts(text, lang, request_id):
            return

        speaker = self._process_speech_social_context(text)

        if self._handle_blocked_or_special_commands(text, speaker, lang):
            return

        if self._handle_offline_mode(text, lang):
            return

        try:
            if self._try_agent_core_path(text, lang, speaker, request_id):
                return
            self._try_direct_llm_path(text, lang, speaker, request_id)
        except Exception as exc:
            logger.error("Failed to generate reply: %s", exc)
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
            self._check_darkness_appraisal(time.time())
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
            self.appraise_event("rested")
            if hasattr(self.mood, "satisfy_need"):
                rest_fill = float(
                    self.config.get("defaults", {}).get("mood", {}).get("needs", {}).get("rest", {}).get("sleep_fill", 35)
                )
                self.mood.satisfy_need("rest", rest_fill)
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            if not self._run_scene("wake_entry", context={"hour": hour}):
                self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)


# BEGIN BATCH04 PI HARDWARE OWNER TOPO PATCH

def _batch04_model_asset_status(self):
    try:
        from modules.common.model_asset_truth import collect_asset_truth
        return collect_asset_truth(Path.cwd())
    except Exception as exc:
        return {"ok": False, "available": False, "error": str(exc)}

def _batch04_pi_runtime_status(self):
    try:
        from modules.autonomy.services.pi_hardware_runtime import PiHardwareRuntime
        cfg = self.config.get("pi_hardware_runtime", {}) if isinstance(self.config.get("pi_hardware_runtime", {}), dict) else {}
        return PiHardwareRuntime(cfg, client=self.client).status()
    except Exception as exc:
        return {"ok": False, "available": False, "error": str(exc)}

def _batch04_topomap_executor(self):
    from modules.autonomy.services.topomap_motion_executor import TopomapMotionExecutor
    cfg = self.config.get("topomap_motion", {}) if isinstance(self.config.get("topomap_motion", {}), dict) else {}
    cur = getattr(self, "_batch04_topomap_motion", None)
    if cur is None:
        cur = TopomapMotionExecutor(cfg, client=self.client); setattr(self, "_batch04_topomap_motion", cur)
    return cur

def _batch04_navigation_topomap(self):
    try: return _batch04_topomap_executor(self).list_map()
    except Exception as exc: return {"ok": False, "available": False, "error": str(exc)}

def _batch04_navigation_learn_place(self, payload=None):
    try:
        result = _batch04_topomap_executor(self).learn_place(payload or {})
        try:
            place = result.get("place") if isinstance(result, dict) else {}
            if isinstance(place, dict) and hasattr(self, "observe_world_memory"):
                self.observe_world_memory({"kind": "place", "name": place.get("name") or place.get("id"), "summary": place.get("summary") or "learned navigation place", "confidence": place.get("safety_score", 0.6), "salience": 0.7, "tags": ["place", "topomap", str(place.get("kind") or "place")], "details": place}, source="topomap_motion")
        except Exception: pass
        return result
    except Exception as exc: return {"ok": False, "available": False, "error": str(exc)}

def _batch04_navigation_goal(self, payload=None):
    try:
        result = _batch04_topomap_executor(self).execute_goal(payload or {}); self.state["topomap_motion"] = result; return result
    except Exception as exc:
        result = {"ok": False, "available": False, "error": str(exc)}; self.state["topomap_motion"] = result; return result

def _batch04_owner_learning(self):
    from modules.autonomy.services.owner_person_learning import OwnerPersonLearning
    cfg = self.config.get("owner_learning", {}) if isinstance(self.config.get("owner_learning", {}), dict) else {}
    cur = getattr(self, "_batch04_owner_learning", None)
    if cur is None:
        cur = OwnerPersonLearning(cfg, client=self.client, memory=getattr(self, "world_memory", None)); setattr(self, "_batch04_owner_learning", cur)
    return cur

def _batch04_owner_status(self):
    try: return _batch04_owner_learning(self).status()
    except Exception as exc: return {"ok": False, "available": False, "error": str(exc)}

def _batch04_owner_learn(self, payload=None):
    try: return _batch04_owner_learning(self).learn(payload or {})
    except Exception as exc: return {"ok": False, "available": False, "error": str(exc)}

def _batch04_owner_identify(self, payload=None):
    try:
        result = _batch04_owner_learning(self).identify(payload or {}); self.state["owner_identification"] = result; return result
    except Exception as exc:
        result = {"ok": False, "available": False, "error": str(exc)}; self.state["owner_identification"] = result; return result

def _batch04_companion_e2e_scenario(self, payload=None):
    body = payload if isinstance(payload, dict) else {}; actions = []
    try: needs = self.tick_living_needs() if hasattr(self, "tick_living_needs") else {}
    except Exception as exc: needs = {"ok": False, "error": str(exc)}
    try: owner = _batch04_owner_identify(self, {})
    except Exception as exc: owner = {"ok": False, "error": str(exc)}
    try: tracks = self.client._get("camera", "/tracking/tracks", timeout_s=0.8)
    except Exception as exc: tracks = {"ok": False, "error": str(exc)}
    no_person = True
    if isinstance(tracks, dict):
        items = tracks.get("tracks") if isinstance(tracks.get("tracks"), list) else []
        no_person = not any(str(t.get("label") or "").lower() == "person" for t in items if isinstance(t, dict))
    if bool(body.get("force_rest")) or no_person:
        try: actions.append({"type": "rest_corner", "result": self.execute_safe_rest_corner({"reason": "e2e_no_person", "allow_base_motion": bool(body.get("allow_base_motion", False))})})
        except Exception as exc: actions.append({"type": "rest_corner", "ok": False, "error": str(exc)})
    if bool(body.get("sound_interrupt")):
        try: actions.append({"type": "sound_interrupt", "result": self.handle_sound_interrupt({"event_type": "sound", "source": "e2e"})})
        except Exception as exc: actions.append({"type": "sound_interrupt", "ok": False, "error": str(exc)})
    try: memory = self.get_world_memory_context(str(body.get("query") or "owner safe place current room"), limit=5) if hasattr(self, "get_world_memory_context") else {}
    except Exception as exc: memory = {"ok": False, "error": str(exc)}
    result = {"ok": True, "available": True, "mode": body.get("mode") or "safe", "needs": needs, "owner": owner, "tracks": tracks, "no_person": no_person, "actions": actions, "memory_context": memory}
    self.state["companion_e2e_scenario"] = result; return result

AutonomyBrain.get_model_asset_status = _batch04_model_asset_status
AutonomyBrain.get_pi_runtime_status = _batch04_pi_runtime_status
AutonomyBrain.get_navigation_topomap = _batch04_navigation_topomap
AutonomyBrain.learn_navigation_topomap_place = _batch04_navigation_learn_place
AutonomyBrain.execute_navigation_goal = _batch04_navigation_goal
AutonomyBrain.get_owner_learning_status = _batch04_owner_status
AutonomyBrain.learn_owner_person = _batch04_owner_learn
AutonomyBrain.identify_owner_person = _batch04_owner_identify
AutonomyBrain.run_companion_e2e_scenario = _batch04_companion_e2e_scenario
# END BATCH04 PI HARDWARE OWNER TOPO PATCH
