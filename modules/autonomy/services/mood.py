import time
import logging

logger = logging.getLogger("autonomy.mood")

class MoodManager:
    def __init__(self, config):
        self.config = config
        defaults = config.get("defaults", {}).get("mood", {})
        
        self.state = {
            "happiness": defaults.get("initial_happiness", 50),
            "energy": defaults.get("initial_energy", 100),
            "curiosity": 50,
            "fear": 0
        }
        
        self.last_update = time.time()
        
    def update(self):
        """Called periodically to decay/update moods"""
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        
        decay = self.config.get("defaults", {}).get("mood", {}).get("decay_rate", 0.1) * dt
        
        # Natural decay/recovery
        self.state["happiness"] = max(0, self.state["happiness"] - (decay * 0.5))
        self.state["energy"] = max(0, self.state["energy"] - (decay * 0.2))
        self.state["curiosity"] = min(100, self.state["curiosity"] + (decay * 0.5)) # Curiosity grows when idle
        self.state["fear"] = max(0, self.state["fear"] - (decay * 2.0)) # Fear recovers quickly
        
    def modify(self, mood, delta):
        if mood in self.state:
            self.state[mood] = max(0, min(100, self.state[mood] + delta))
            
    def get_dominant_emotion(self):
        # Simple logic to determine dominant emotion for LED/Expression
        if self.state["fear"] > 50:
            return "fear"
        if self.state["happiness"] > 70:
            return "joy"
        if self.state["happiness"] < 30:
            return "sadness"
        if self.state["curiosity"] > 80:
            return "curiosity"
        if self.state["energy"] < 20:
            return "tired"
        return "neutral"

    def __getitem__(self, key):
        return self.state.get(key)
