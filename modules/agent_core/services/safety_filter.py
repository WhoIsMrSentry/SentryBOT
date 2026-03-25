import logging
from typing import Dict, Any, List

logger = logging.getLogger("agent.safety_filter")

class ActionSafetyFilter:
    """
    Sits between the Validator and the Planner/Executor to ensure
    no valid JSON actions ask the robot to perform physically
    damaging or dangerous actions.
    """
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = {}
        # Load from config or use safe defaults
        self.max_servo = config.get("safety", {}).get("max_servo_angle", 180)
        self.min_servo = config.get("safety", {}).get("min_servo_angle", 0)
        self.max_stepper = config.get("safety", {}).get("max_stepper_speed", 100)
        self.max_laser = config.get("safety", {}).get("laser_max_duration_s", 2.0)

    def filter_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given a single action dict, clamps its attributes to safe ranges.
        """
        act_type = action.get("type", "")
        attrs = action.get("attrs", {})
        
        safe_action = {"type": act_type, "attrs": {}}
        
        try:
            if act_type == "servo":
                if "pan" in attrs:
                    pan = max(self.min_servo, min(int(attrs["pan"]), self.max_servo))
                    safe_action["attrs"]["pan"] = pan
                if "tilt" in attrs:
                    tilt = max(self.min_servo, min(int(attrs["tilt"]), self.max_servo))
                    safe_action["attrs"]["tilt"] = tilt
                    
            elif act_type == "stepper":
                # Pass through stepper id and mode
                if "id" in attrs:
                    safe_action["attrs"]["id"] = attrs["id"]
                if "mode" in attrs:
                    safe_action["attrs"]["mode"] = attrs["mode"]
                # Clamp velocity/value (both key names are used across the pipeline)
                for vel_key in ("velocity", "value"):
                    if vel_key in attrs:
                        vel = int(attrs[vel_key])
                        sign = 1 if vel >= 0 else -1
                        safe_vel = min(abs(vel), self.max_stepper) * sign
                        safe_action["attrs"][vel_key] = safe_vel
                if "distance" in attrs:
                    safe_action["attrs"]["distance"] = attrs["distance"]
                if "drive" in attrs:
                    safe_action["attrs"]["drive"] = attrs["drive"]
                    
            elif act_type == "laser":
                if "duration" in attrs:
                    dur = min(float(attrs["duration"]), self.max_laser)
                    safe_action["attrs"]["duration"] = dur
                if "state" in attrs:
                    safe_action["attrs"]["state"] = attrs["state"]
            
            else:
                # Other actions (anim, lights, speak) are passed directly through
                safe_action["attrs"] = attrs.copy()

        except ValueError as e:
            logger.warning(f"SafetyFilter: Invalid attribute type in {act_type}, rejecting attrs. ({e})")
            safe_action["attrs"] = {}
            
        return safe_action

    def filter_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run safely filter over a list of actions and return clamped elements.
        """
        safe_list = []
        for act in actions:
            if not isinstance(act, dict):
                continue
            safe_list.append(self.filter_action(act))
        return safe_list
