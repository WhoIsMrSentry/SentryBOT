from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .brain_init import BrainInitMixin
from .brain_parts import (
    AnimationSupportMixin,
    CapabilityHealthMixin,
    CompanionScenarioMixin,
    DecisionMixin,
    EmotionSyncMixin,
    NavigationTopomapMixin,
    OwnerGuardMixin,
    PerceptionContextMixin,
    ResponseTagMixin,
    SceneMixin,
    SpeechReactMixin,
    TimelineMixin,
    VisionMixin,
    VocalMixin,
    WorldMemoryMixin,
)

logger = logging.getLogger("autonomy")

_PAUSED_OPERATIONAL = frozenset({"sleep", "maintenance", "paused", "off", "shutdown", "resting"})


class AutonomyBrain(
    BrainInitMixin,
    AnimationSupportMixin,
    CapabilityHealthMixin,
    CompanionScenarioMixin,
    DecisionMixin,
    EmotionSyncMixin,
    NavigationTopomapMixin,
    OwnerGuardMixin,
    PerceptionContextMixin,
    ResponseTagMixin,
    SceneMixin,
    SpeechReactMixin,
    TimelineMixin,
    VisionMixin,
    VocalMixin,
    WorldMemoryMixin,
):
    """Proactive life-loop planner. Agent_core orchestrates one LLM turn; this class owns whether to act.

    See `.sentrybot/context/behavior-authority.md`.
    """

    def __init__(self, config: dict[str, Any]):
        self._init_components(config)

    def start(self) -> None:
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

    def stop(self) -> None:
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
        if getattr(self, "_worker_executor", None) is not None:
            try:
                self._worker_executor.shutdown(wait=False)
            except Exception:
                pass
        logger.info("AutonomyBrain stopped.")

    def _loop(self) -> None:
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

    def interaction_occurred(self, source: str = "unknown") -> None:
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

    def _sense(self) -> None:
        self._sense_sound_direction()
        self._sense_speech_text()
        self._sense_visual_tracking()

    def _sense_sound_direction(self) -> None:
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
                now = time.time()
                last_time = float(self.state.get("last_sound_time", 0.0) or 0.0)
                last_angle = self.state.get("last_sound_angle", None)
                if last_angle is None or abs(float(raw_angle) - float(last_angle)) >= 15.0 or (now - last_time) >= 15.0:
                    self.state["last_sound_time"] = now
                    self.state["last_sound_angle"] = raw_angle
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

    def _sense_speech_text(self) -> None:
        try:
            text = None
            source_lang = None
            ts = 0.0
            if hasattr(self.client, "get_speech_text"):
                text = self.client.get_speech_text()
            elif hasattr(self.client, "get_last_speech"):
                speech_obj = self.client.get_last_speech()
                if isinstance(speech_obj, dict) and speech_obj.get("final"):
                    text = speech_obj.get("text")
                    source_lang = speech_obj.get("language")
                    ts = float(speech_obj.get("ts", 0.0) or 0.0)
            if text and text.strip():
                self.on_speech_final(text, source_lang=source_lang, ts=ts)
        except Exception as e:
            logger.debug(f"Failed to fetch speech text: {e}")
