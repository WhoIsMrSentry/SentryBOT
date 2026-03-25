import json
from datetime import datetime
from typing import Dict, Any

class WorldState:
    """
    Maintains the real-time context of the robot.
    Added Chrono-awareness, Location mapping, and Action Outcome handling.
    """
    def __init__(self):
        self.state: Dict[str, Any] = {
            "distance_front_cm": -1,
            "battery_percent": 100,
            "person_detected": False,
            "last_rfid": None,
            "is_moving": False,
            "location": "unknown",
            "last_action_feedback": "None" # Success or motor stall errors
        }
        
    def update_state(self, updates: Dict[str, Any]):
        self.state.update(updates)
        
    def set_action_feedback(self, feedback: str):
        self.state["last_action_feedback"] = feedback
        
    def get_state(self) -> Dict[str, Any]:
        return self.state.copy()
        
    def inject_world_state(self, base_prompt: str) -> str:
        """
        Injects real-time state plus Chrono-awareness into the LLM context.
        """
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        hour = now.hour
        
        # Chrono-awareness heuristic
        time_of_day = "Night"
        if 6 <= hour < 12:
            time_of_day = "Morning"
        elif 12 <= hour < 18:
            time_of_day = "Afternoon"
        elif 18 <= hour < 22:
            time_of_day = "Evening"
            
        chrono = {
            "datetime": time_str,
            "time_of_day": time_of_day
        }
        
        context = {
            "chrono": chrono,
            "sensors": self.state
        }
        
        state_str = json.dumps(context, indent=2)
        injected = f"{base_prompt}\n\n[SYSTEM WORLD STATE]\n{state_str}\n"
        return injected
