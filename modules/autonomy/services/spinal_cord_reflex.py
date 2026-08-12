import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.spinal_cord")

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
                self._last_reflex_ts = now
                # Notify the higher brain (LLM/Memory) so it knows *why* it stopped
                try:
                    self.memory.add_event(f"I performed a reflex action: {action_taken}. I should express surprise or explain why I stopped.")
                    # Trigger a surprised or shocked expression immediately
                    self.client.update_emotions(["surprise"])
                    self.client.push_interaction_event("appraisal:shocked")
                except Exception as exc:
                    logger.error(f"Failed to notify higher brain of reflex: {exc}")
                return True

        except Exception as exc:
            logger.error(f"Error executing spinal cord reflex: {exc}")

        return False
