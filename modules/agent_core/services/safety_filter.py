# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_argument_safety_filter'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime safety policy and capability map: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ActionSafetyFilter still clamps action handler arguments inside AgentOrchestrator. Keep stable as a local argument clamp helper.'
# --- End SentryBOT safety/action boundary contract ---

import logging
from typing import Dict, Any

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
