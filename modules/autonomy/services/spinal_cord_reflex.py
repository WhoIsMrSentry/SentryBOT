import logging
import threading
import time
from typing import Any, Dict

logger = logging.getLogger("autonomy.spinal_cord")


def _extract_voice_emergency_flag(laya_decision: Any) -> bool:
    """Resolve emergency flag across LayaDecision objects, dicts, or emergency tokens."""
    if isinstance(laya_decision, dict):
        if "is_emergency" in laya_decision:
            return bool(laya_decision.get("is_emergency"))
        target = str(laya_decision.get("target_module") or "").strip().lower()
        return target == "emergency_stop"
    if hasattr(laya_decision, "is_emergency"):
        return bool(getattr(laya_decision, "is_emergency", False))
    try:
        from modules.agent_core.services.laya_engine import LayaEngine

        if callable(getattr(LayaEngine, "is_emergency_decision", None)):
            # Respect Laya decision objects even if custom-wrapped
            return bool(getattr(laya_decision, "target_module", "") == "emergency_stop")
    except Exception:
        pass
    return False


class SpinalCordReflexEngine:
    """
    Spinal Cord Reflex System (Omurilik Refleks Sistemi).
    Acts as a high-priority, low-latency interceptor for hardware events,
    bypassing the slower LLM/BehaviorPlanner for emergency reactions.
    """

    def __init__(self, config: Dict[str, Any], client: Any, memory: Any):
        self.config = config
        self.client = client
        self.memory = memory  # Typically ShortTermMemory
        self.enabled = bool(self.config.get("enabled", True))
        self.reflex_cooldown_s = float(self.config.get("cooldown_s", 2.0))
        self._last_reflex_ts = 0.0
        self._lock = threading.RLock()

    def _notify_higher_brain(self, event_message: str) -> None:
        """Notify higher cognitive layers (memory + expression) after a spinal reflex."""
        try:
            if self.memory is not None and hasattr(self.memory, "add_event"):
                self.memory.add_event(event_message)
            if self.client is not None:
                if hasattr(self.client, "update_emotions"):
                    self.client.update_emotions(["surprise"])
                if hasattr(self.client, "push_interaction_event"):
                    self.client.push_interaction_event("appraisal:shocked")
        except Exception as exc:
            logger.error("Failed to notify higher brain of reflex: %s", exc)

    def observe_hardware_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """
        Receives raw hardware events (e.g., cliff_detected, impact, obstacle).
        Returns True if a reflex action was taken, False otherwise.
        """
        if not self.enabled:
            return False

        now = time.time()
        if now - self._last_reflex_ts < self.reflex_cooldown_s:
            # Prevent spamming reflexes
            return False

        event_type = str(event_type).strip().lower()
        reflex_triggered = False
        action_taken = ""

        try:
            if event_type == "cliff_detected" or event_type == "cliff":
                logger.warning("SPINAL CORD REFLEX: Cliff detected! Halting and reversing.")
                self.client.push_interaction_event("motor.stop", {"priority": "emergency"})
                self.client.push_interaction_event("motor.move", {"direction": "backward", "speed": 100, "duration": 0.5})
                action_taken = "emergency stop and reverse due to cliff"
                reflex_triggered = True

            elif event_type == "impact" or event_type == "bump":
                logger.warning("SPINAL CORD REFLEX: Impact detected! Halting.")
                self.client.push_interaction_event("motor.stop", {"priority": "emergency"})
                action_taken = "emergency stop due to impact"
                reflex_triggered = True

            elif event_type == "obstacle_imminent" or event_type == "ultra_dist":
                # Some firmware sends distance in 'cm', others in 'distance_cm'
                distance = payload.get("distance_cm", payload.get("cm", 999))
                if distance < 10:
                    logger.warning(f"SPINAL CORD REFLEX: Obstacle too close ({distance}cm)! Halting.")
                    self.client.push_interaction_event("motor.stop", {"priority": "emergency"})
                    action_taken = "emergency stop due to close obstacle"
                    reflex_triggered = True
            
            if reflex_triggered:
                with self._lock:
                    self._last_reflex_ts = now
                self._notify_higher_brain(
                    f"I performed a reflex action: {action_taken}. I should express surprise or explain why I stopped."
                )
                return True

        except Exception as exc:
            logger.error(f"Error executing spinal cord reflex: {exc}")

        return False

    def observe_voice_emergency(self, laya_decision: Any) -> bool:
        """Trigger spinal cord reflex from a Laya emergency voice decision."""
        if not self.enabled or not _extract_voice_emergency_flag(laya_decision):
            return False

        now = time.time()
        with self._lock:
            if now - self._last_reflex_ts < self.reflex_cooldown_s:
                return False
            self._last_reflex_ts = now

        urgency = float(
            laya_decision.get("urgency_score", 0.0)
            if isinstance(laya_decision, dict)
            else getattr(laya_decision, "urgency_score", 0.0)
        )
        target = str(
            laya_decision.get("target_module", "unknown")
            if isinstance(laya_decision, dict)
            else getattr(laya_decision, "target_module", "unknown")
        )
        logger.warning(
            "SPINAL CORD REFLEX: Voice emergency detected via Laya! target=%s urgency=%.1f",
            target, urgency,
        )

        try:
            self.client.push_interaction_event("motor.stop", {"priority": "emergency", "source": "laya_voice"})
        except Exception as exc:
            logger.error("Failed to send emergency stop from voice: %s", exc)

        self._notify_higher_brain(
            f"Voice emergency detected: urgency={urgency:.1f}, target={target}. "
            "Motor stopped via spinal cord reflex."
        )
        return True
