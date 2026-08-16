from __future__ import annotations

import datetime
import json
import logging
import random
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .affective_appraisal import AffectiveAppraisal
from .appraisal_triggers import speech_appraisal_event
from .audio_event_needs_bridge import AudioEventNeedsBridge
from .barge_in import BargeInController
from .behavior_shadow_learner import BehaviorShadowLearner
from .brain_parts import (
    AnimationSupportMixin,
    CapabilityHealthMixin,
    CompanionScenarioMixin,
    NavigationTopomapMixin,
    OwnerGuardMixin,
    PerceptionContextMixin,
    ResponseTagMixin,
    SceneMixin,
    TimelineMixin,
    VisionMixin,
    VocalMixin,
    WorldMemoryMixin,
)
from .client import ServiceClient
from .companion_auto_execute_gate import CompanionAutoExecuteGate
from .companion_goal_executor import CompanionGoalExecutor
from .companion_goal_selector import CompanionGoalSelector
from .companion_lines import CompanionLineGenerator
from .companion_rituals import CompanionRituals
from .expression_director import ExpressionDirector
from .idle_behaviors import IdleBehaviorPlanner
from .interaction_feedback import InteractionFeedbackLearner
from .liveliness import LivelinessScheduler
from .living_needs import LivingNeedsEngine
from .memory import ShortTermMemory
from .memory_decision_shadow import MemoryDecisionShadow
from .memory_needs_bias import MemoryNeedsBias
from .mood import MoodManager
from .needs_engine import CompanionNeedsEngine
from .proactive_planner import ProactivePlanner
from .reflection_planner import ReflectionPlanner
from .relationship_memory import RelationshipMemory
from .safe_navigation import SafeNavigationMemory
from .spinal_cord_reflex import SpinalCordReflexEngine
from .vision_context_needs_bridge import VisionContextNeedsBridge
from .world_memory_autowriter import WorldMemoryAutoWriter
from .world_memory_rag import WorldMemoryRAG as WorldMemory

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
    CapabilityHealthMixin,
    CompanionScenarioMixin,
    NavigationTopomapMixin,
    OwnerGuardMixin,
    PerceptionContextMixin,
    ResponseTagMixin,
    SceneMixin,
    TimelineMixin,
    VisionMixin,
    VocalMixin,
    WorldMemoryMixin,
):
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.running = False
        self.thread: Optional[threading.Thread] = None

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
        learning_cfg = (
            companion_cfg.get("learning", {}) if isinstance(companion_cfg.get("learning", {}), dict) else {}
        )
        self.feedback_learner = InteractionFeedbackLearner(learning_cfg.get("feedback", learning_cfg))
        needs_cfg = (
            self.config.get("companion_needs", {})
            if isinstance(self.config.get("companion_needs", {}), dict)
            else {}
        )
        self.needs_engine = CompanionNeedsEngine(needs_cfg)
        goal_cfg = (
            self.config.get("companion_goals", {})
            if isinstance(self.config.get("companion_goals", {}), dict)
            else {}
        )
        self.goal_selector = CompanionGoalSelector(goal_cfg)
        executor_cfg = (
            self.config.get("companion_goal_executor", {})
            if isinstance(self.config.get("companion_goal_executor", {}), dict)
            else {}
        )
        self.goal_executor = CompanionGoalExecutor(executor_cfg, client=self.client)
        auto_exec_cfg = (
            self.config.get("companion_auto_execute", {})
            if isinstance(self.config.get("companion_auto_execute", {}), dict)
            else {}
        )
        self.goal_auto_execute_gate = CompanionAutoExecuteGate(auto_exec_cfg)
        self.reflection_planner = ReflectionPlanner(config)
        vision_needs_cfg = (
            self.config.get("vision_context_needs", {})
            if isinstance(self.config.get("vision_context_needs", {}), dict)
            else {}
        )
        self.vision_context_needs_bridge = VisionContextNeedsBridge(vision_needs_cfg)
        audio_needs_cfg = (
            self.config.get("audio_event_needs", {})
            if isinstance(self.config.get("audio_event_needs", {}), dict)
            else {}
        )
        self.audio_event_needs_bridge = AudioEventNeedsBridge(audio_needs_cfg)
        world_memory_cfg = (
            self.config.get("world_memory", {})
            if isinstance(self.config.get("world_memory", {}), dict)
            else {}
        )
        self.world_memory = WorldMemory(world_memory_cfg)
        living_needs_cfg = (
            self.config.get("living_needs", {})
            if isinstance(self.config.get("living_needs", {}), dict)
            else {}
        )
        self.living_needs = LivingNeedsEngine(living_needs_cfg)
        safe_navigation_cfg = (
            self.config.get("safe_navigation", {})
            if isinstance(self.config.get("safe_navigation", {}), dict)
            else {}
        )
        self.safe_navigation = SafeNavigationMemory(safe_navigation_cfg, client=self.client)
        memory_decision_cfg = (
            self.config.get("memory_decision_shadow", {})
            if isinstance(self.config.get("memory_decision_shadow", {}), dict)
            else {}
        )
        self.memory_decision_shadow = MemoryDecisionShadow(memory_decision_cfg)
        memory_bias_cfg = (
            self.config.get("memory_needs_bias", {})
            if isinstance(self.config.get("memory_needs_bias", {}), dict)
            else {}
        )
        self.memory_needs_bias = MemoryNeedsBias(memory_bias_cfg)
        world_memory_autowrite_cfg = (
            self.config.get("world_memory_autowrite", {})
            if isinstance(self.config.get("world_memory_autowrite", {}), dict)
            else {}
        )
        self.world_memory_autowriter = WorldMemoryAutoWriter(world_memory_autowrite_cfg)
        self.barge_in = BargeInController(
            config.get("barge_in", {}) if isinstance(config.get("barge_in", {}), dict) else {}
        )
        self.liveliness = LivelinessScheduler(
            config.get("liveliness", {}) if isinstance(config.get("liveliness", {}), dict) else {}
        )
        self._vision_cfg = config.get("vision_hooks", {})
        self.owner_cfg = config.get("owner", {})

        spinal_cfg = (
            self.config.get("spinal_cord", {})
            if isinstance(self.config.get("spinal_cord", {}), dict)
            else {}
        )
        self.spinal_cord = SpinalCordReflexEngine(spinal_cfg, client=self.client, memory=self.memory)

        shadow_cfg = (
            self.config.get("shadow_learner", {})
            if isinstance(self.config.get("shadow_learner", {}), dict)
            else {}
        )
        self.shadow_learner = BehaviorShadowLearner(shadow_cfg)

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
                logger.info("Agent Core integrated successfully (provider=%s model=%s).", provider, model)
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
        self._speech_min_interval_s = float(
            self.config.get("request_timeouts", {}).get("speech_min_interval_s", 0.35)
        )
        visuals_cfg = (
            self.config.get("visual_state", {})
            if isinstance(self.config.get("visual_state", {}), dict)
            else {}
        )
        self._visual_emotion_min_interval_s = float(visuals_cfg.get("emotion_min_interval_s", 2.0))
        self._visual_lock_default_s = float(visuals_cfg.get("default_lock_s", 2.2))
        self._visual_lock_strong_s = float(visuals_cfg.get("strong_lock_s", 4.5))
        self._visual_state_hold_s = float(visuals_cfg.get("state_hold_s", 3.0))
        self._visual_strong_emotions = {
            str(x).strip().lower()
            for x in (visuals_cfg.get("strong_emotions", ["fear", "angry", "furious"]) or [])
            if str(x).strip()
        }
        graph_cfg = (
            visuals_cfg.get("transition_graph", {})
            if isinstance(visuals_cfg.get("transition_graph", {}), dict)
            else {}
        )
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
                self.client.warmup_models()
            except Exception:
                pass

        if getattr(self, "agent", None):
            try:
                self.agent.start()
            except Exception as exc:
                logger.warning("Failed to start AgentOrchestrator loop: %s", exc)

        self.thread = threading.Thread(target=self._loop, name="autonomy_brain", daemon=True)
        self.thread.start()
        logger.info("AutonomyBrain started.")

    def stop(self):
        self.running = False
        if getattr(self, "agent", None) and hasattr(self.agent, "stop"):
            try:
                self.agent.stop()
            except Exception:
                pass
        thread = getattr(self, "thread", None)
        if thread is not None and hasattr(thread, "join"):
            try:
                if hasattr(thread, "is_alive") and not thread.is_alive():
                    pass
                else:
                    thread.join()
            except Exception:
                pass
        logger.info("AutonomyBrain stopped.")

    def _loop(self):
        logger.info("Brain main loop running.")
        poll_interval = float(self.config.get("defaults", {}).get("poll_interval_s", 0.5))
        while self.running:
            try:
                self._sense()
                self._think()
            except Exception as e:
                logger.error(f"Error in brain loop: {e}", exc_info=True)
            time.sleep(poll_interval)

    def handle_hardware_event(self, event_name: str, payload: dict | None = None) -> dict:
        if self.spinal_cord:
            return self.spinal_cord.handle_event(event_name, payload)
        return {"handled": False, "reason": "no_spinal_cord"}

    def observe_manual_action(self, action_type: str, payload: dict | None = None) -> None:
        if self.shadow_learner:
            self.shadow_learner.observe(action_type, payload or {}, context={"mood": self.mood.get_dominant_emotion()})

    def interaction_occurred(self, source: str = "unknown"):
        self.state["last_interaction"] = time.time()
        self.state["is_bored"] = False
        self.mood.modify("happiness", 2)
        if self.feedback_learner and hasattr(self.feedback_learner, "record_activity"):
            self.feedback_learner.record_activity()
        if source != "sound":
            if hasattr(self.liveliness, "record_interaction"):
                self.liveliness.record_interaction()
            if self._companion_paused() and not self.state.get("is_sleeping"):
                try:
                    mode = self.client.get_operational_mode()
                    if str(mode).strip().lower() in {"paused", "resting"}:
                        self.client.set_operational_mode("active")
                except Exception:
                    pass

    def _sense(self):
        self._sense_sound_direction()
        self._sense_speech_text()
        self._sense_visual_tracking()

    def _sense_sound_direction(self):
        try:
            raw_angle = None
            if hasattr(self.client, "get_sound_direction"):
                raw_angle = self.client.get_sound_direction()
            elif hasattr(self.client, "get_speech_direction"):
                dir_obj = self.client.get_speech_direction()
                if isinstance(dir_obj, dict):
                    raw_angle = dir_obj.get("angle")
                elif isinstance(dir_obj, (int, float)):
                    raw_angle = dir_obj
            if raw_angle is not None:
                self.interaction_occurred("sound")
                logger.info("Processing sound direction: %s", raw_angle)
                self._react_to_sound(raw_angle)
        except Exception as e:
            logger.debug(f"Failed to fetch sound direction: {e}")

    def _companion_paused(self) -> bool:
        try:
            mode = self.client.get_operational_mode()
            if str(mode).strip().lower() in _PAUSED_OPERATIONAL:
                return True
        except Exception:
            pass
        return False

    def on_speech_final(self, text: str, source_lang: str | None = None) -> None:
        if not text or not text.strip():
            return
        t = text.strip()
        last_text = str(self.state.get("last_speech_text") or "").strip()
        now = time.time()
        if t == last_text and (now - float(self.state.get("last_speech_time", 0.0) or 0.0)) < self._speech_min_interval_s:
            logger.debug("Suppressing duplicate speech delivery within debounce window: %s", t)
            return
        self.state["last_speech_text"] = t
        self.state["last_speech_time"] = now
        self._dispatch_final_speech(t, source_lang=source_lang)

    def _dispatch_final_speech(self, text: str, source_lang: str | None = None) -> None:
        self.interaction_occurred("speech")
        detected_lang = source_lang
        if not detected_lang and detect_text_language:
            detected_lang = detect_text_language(text, default="tr")
        if detected_lang:
            self.state["last_speech_language"] = detected_lang
        try:
            self.client.push_interaction_event("speech.final", {"text": text, "lang": detected_lang or "tr"})
            self.client.set_oled_stt_text(text)
        except Exception:
            pass
        self._react_to_speech(text, source_lang=detected_lang)

    def _sense_speech_text(self):
        try:
            text = None
            source_lang = None
            if hasattr(self.client, "get_speech_text"):
                text = self.client.get_speech_text()
            elif hasattr(self.client, "get_last_speech"):
                speech_obj = self.client.get_last_speech()
                if isinstance(speech_obj, dict) and speech_obj.get("final"):
                    text = speech_obj.get("text")
                    source_lang = speech_obj.get("language")
            if text and text.strip():
                self.on_speech_final(text, source_lang=source_lang)
        except Exception as e:
            logger.debug(f"Failed to fetch speech text: {e}")

    def _sync_emotion(self):
        dominant = self.mood.get_dominant_emotion()
        if dominant != self.state["last_emotion"]:
            self.state["last_emotion"] = dominant
            logger.info("Emotion shifted to %s", dominant)
            self._apply_timeline_event(f"emotion_{dominant}")
            self._update_timeline_emotion(dominant)
            self.client.push_interaction_event(f"mood.{dominant}")

        now = time.time()
        if now - self._last_emotion_sync_ts >= self._visual_emotion_min_interval_s:
            self._last_emotion_sync_ts = now
            chosen = self._select_visual_emotion(dominant)
            if chosen != self._last_emotion_sent:
                self.client.update_emotions([chosen])
                self._last_emotion_sent = chosen

    @staticmethod
    def _emotion_scene_name(canon: str) -> str:
        visual = AutonomyBrain._normalize_emotion_name(canon)
        return f"emotion_{visual}"

    def express(
        self,
        emotion: str,
        say: str | None = None,
        duration: float = 3.0,
        scene: str | None = None,
        language: str | None = None,
    ) -> str:
        try:
            from modules.common.emotion_vocab import get_vocab

            canon = get_vocab().canonical(emotion)
        except Exception:
            canon = str(emotion or "neutral").lower()

        logger.info("Expressing emotion %s (canonical: %s)", emotion, canon)
        self._apply_emotion_visual_state(canon)
        if say:
            self._speak_with_mood(say, emotion=canon, language=language)
        scene_name = scene or self._emotion_scene_name(canon)
        try:
            self._run_scene(scene_name, context={"emotion": canon, "duration": duration})
        except Exception as exc:
            logger.debug("Scene for express failed: %s", exc)
        return canon

    def appraise_event(self, event_name: str, intensity: float = 1.0, emit: bool = True) -> bool:
        if self._companion_paused() and not self.state.get("is_sleeping"):
            return False
        result = self.appraisal.process_event(event_name, intensity=intensity)
        if not result or not result.get("matched"):
            return False
        for axis, delta in result.get("mood_deltas", {}).items():
            self.mood.modify(axis, delta)
        self.state["last_appraisal"] = result
        if emit:
            payload = {
                "event": event_name,
                "intensity": intensity,
                "deltas": result.get("mood_deltas"),
                "notes": result.get("notes"),
            }
            self.client.push_interaction_event(f"appraisal:{event_name}", payload)
        self._sync_emotion()
        return True

    @staticmethod
    def _sentiment_event_for_text(text: str) -> str | None:
        return speech_appraisal_event(text)

    def _maybe_emit_speech_excited(self, text: str, sentiment_event: str | None) -> None:
        reactions_cfg = self.config.get("speech_reactions", {}) if isinstance(self.config.get("speech_reactions"), dict) else {}
        t = str(text or "")
        if reactions_cfg:
            excited_on_speech = bool(reactions_cfg.get("excited_on_speech", False))
            excited_on_praise = bool(reactions_cfg.get("excited_on_praise", False))
            excited_on_questions = bool(reactions_cfg.get("excited_on_questions", False))

            if excited_on_speech:
                self.client.push_interaction_event("autonomy.excited")
                return
            if excited_on_praise and sentiment_event in {"user_praise", "praise", "owner_returned"}:
                self.client.push_interaction_event("autonomy.excited")
                return
            if excited_on_questions and "?" in t:
                self.client.push_interaction_event("autonomy.excited")
                return
            return

        positive_sentiment = sentiment_event in {"praise", "user_praise", "owner_returned"}
        exclaimed = "!" in t or positive_sentiment
        if not exclaimed:
            return
        energy = float(self.mood.state.get("energy", 50.0) or 50.0)
        happiness = float(self.mood.state.get("happiness", 50.0) or 50.0)
        if (energy + happiness) >= 110.0:
            self.client.push_interaction_event("speech.excited", {"text": t, "energy": energy, "happiness": happiness})

    _EMOTION_COMMAND_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("anger", ("sinirlen", "kız", "kızgın ol", "öfkelen", "sinirlensene")),
        ("joy", ("mutlu ol", "sevin", "gülümse", "neşelen", "mutlu görün")),
        ("sadness", ("üzül", "hüzünlen", "üzgün ol")),
        ("fear", ("kork", "korkmuş gibi yap", "ürper")),
        ("surprise", ("şaşır", "şaşkın ol")),
        ("bored", ("sıkıl", "ofla", "canın sıkılsın")),
        ("tired", ("yorul", "esne", "uykulu ol")),
        ("love", ("sev beni", "tatlı ol", "şirin ol")),
        ("excitement", ("heyecanlan", "coş")),
        ("neutral", ("sakinleş", "normale dön", "düz dur", "nötr ol")),
    )

    @classmethod
    def _emotion_command_for_text(cls, text: str) -> str | None:
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

            # Dream Cycle: Prune and consolidate memories while sleeping
            last_prune = self.state.get("last_memory_prune_ts", 0)
            if now - last_prune > 3600:
                logger.info("Dream Cycle: Pruning and consolidating memories...")
                try:
                    prune_res = self.world_memory.prune_unimportant_memories()
                    cons_res = self.world_memory.consolidate_memories()
                    logger.info(
                        f"Dream Cycle complete. Pruned: {prune_res.get('deleted', 0)}, "
                        f"Consolidated: {cons_res.get('consolidated', 0)}"
                    )
                except Exception as exc:
                    logger.error(f"Dream cycle failed: {exc}")
                self.state["last_memory_prune_ts"] = now

            return

        self.mood.update()
        self._sync_emotion()
        self._liveliness_tick(now)

        self._update_companion_needs(now)

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
                agentic_enabled = bool(idle_cfg.get("fallback_to_llm", True)) or bool(
                    self.config.get("agentic", {}).get("enabled", True)
                )
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

    def _run_idle_behavior(self, now: float) -> bool:
        choice = self.idle_planner.pick(now=now)
        if choice is None:
            return False
        logger.info("Idle behavior selected: %s", choice.name)
        self.memory.add_event(f"Idle action: {choice.name}")
        self._execute_action(choice.action)
        return True

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
        if float(self.mood.state.get("energy", 100) or 100) <= float(triggers.get("low_energy", 25)):
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

        situation = "You are currently IDLE with unmet needs."
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
            f"- Happiness: {int(self.mood.state['happiness'])}/100, Energy: {int(self.mood.state['energy'])}/100, "
            f"Curiosity: {int(self.mood.state['curiosity'])}/100\n"
            f"- Needs: social={needs.get('social', 0)}, stimulation={needs.get('stimulation', 0)}, "
            f"rest={needs.get('rest', 0)}\n"
            f"Recent Events:\n{events}\n\n"
            f"{social_context}\n"
            f"{('Preferences: ' + pref_summary) if pref_summary else ''}\n"
            f"{('Recent activity: ' + activity) if activity else ''}\n"
            f"{mood_trend}\n{sighting}\n\n"
            f"AVAILABLE PHYSICAL TOOLS (call them, don't just describe):\n"
            f"- express_emotion(emotion, intensity, duration_s, modalities, text?, language?)\n"
            f"- look_around() -- sweep gaze to discover things\n"
            f"- move_head(pan, tilt, duration_s) -- point face\n"
            f"- speak(text, language) -- say something out loud\n"
            f"- set_lights(effect, emotions?, color?, duration?) -- raw NeoPixel\n"
            f"\nPick ONE small in-character action that fits your current mood/needs. "
            f"Do not ask for permission. Act, then briefly confirm."
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

    def _execute_action(self, action: str):
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

    _STRONG_VISUAL_EMOTIONS = {"fear", "furious", "anger", "surprise"}

    def _apply_emotion_visual_state(self, emotion: str) -> None:
        e = str(emotion or "neutral").strip().lower()
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
                    self.config.get("defaults", {})
                    .get("mood", {})
                    .get("needs", {})
                    .get("rest", {})
                    .get("sleep_fill", 35)
                )
                self.mood.satisfy_need("rest", rest_fill)
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            if not self._run_scene("wake_entry", context={"hour": hour}):
                self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)
