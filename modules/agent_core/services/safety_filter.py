# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_argument_safety_filter'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime safety policy and capability map: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ActionSafetyFilter still clamps action handler arguments inside AgentOrchestrator. Keep stable as a local argument clamp helper.'
# --- End SentryBOT safety/action boundary contract ---

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger("agent.safety_filter")

class ActionSafetyFilter:
    """
    Validates and clamps arguments for hardware tools to prevent damage.
    """
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = {}
        safety = config.get("safety", {})
        self.max_servo = safety.get("max_servo_angle", 180)
        self.min_servo = safety.get("min_servo_angle", 0)
        self.max_stepper = safety.get("max_stepper_speed", 100)
        self.max_laser = safety.get("laser_max_duration_s", 2.0)

    def clamp_servo(self, angle: int) -> int:
        return max(self.min_servo, min(int(angle), self.max_servo))

    def clamp_stepper(self, speed: int) -> int:
        sign = 1 if speed >= 0 else -1
        return min(abs(int(speed)), self.max_stepper) * sign

    def clamp_laser_duration(self, duration: float) -> float:
        return min(float(duration), self.max_laser)

    def set_world_state(self, world_state):
        self.world_state = world_state

    def check_action_safety(self, action_type: str, payload: dict) -> dict:
        """
        Evaluate if an action is safe to execute in the current context.
        Returns: {"safe": bool, "reason": str, "message": str}
        """
        # 1. Check Quiet Hours (Sleep mode / Time)
        hour = datetime.now().hour
        is_quiet_hours = (hour >= 23 or hour < 8)
        
        if is_quiet_hours:
            if action_type in ["speak", "sound", "play_sound", "express_emotion"]:
                # Ensure the robot doesn't make loud noises during sleep hours
                # Allow exceptions if priority/safety flags exist in payload, but block by default
                if not payload.get("override_quiet_hours", False):
                    logger.warning(f"SafetyFilter blocked {action_type} due to quiet hours (23:00 - 08:00).")
                    return {
                        "safe": False,
                        "reason": "quiet_hours",
                        "message": "Cannot play sounds or speak during sleep hours."
                    }
                    
        # 2. Check Hardware Limits Contextually (e.g., fast move with low battery)
        if action_type in ["move_direct", "stepper", "pathfind"]:
            # If world_state has battery, we could check it here.
            # Example placeholder:
            # if getattr(self, "world_state", None) and self.world_state.get_battery() < 10:
            #     return {"safe": False, "reason": "low_battery", "message": "Battery too low for movement."}
            pass

        return {"safe": True, "reason": "ok", "message": ""}
