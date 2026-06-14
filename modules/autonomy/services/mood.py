import time
import logging
from typing import Any, Optional

logger = logging.getLogger("autonomy.mood")

class MoodManager:
    def __init__(self, config, social_db: Optional[Any] = None):
        self.config = config
        defaults = config.get("defaults", {}).get("mood", {})

        self.state = {
            "happiness": defaults.get("initial_happiness", 50),
            "energy": defaults.get("initial_energy", 100),
            "curiosity": 50,
            "fear": 0,
            "anger": 0,
        }

        self.last_update = time.time()
        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self._last_snapshot_ts = 0.0
        self._snapshot_interval_s = float(defaults.get("snapshot_interval_s", 30.0))

    def _maybe_snapshot(self) -> None:
        if self._social_db is None:
            return
        now = time.time()
        if now - self._last_snapshot_ts < self._snapshot_interval_s:
            return
        try:
            self._social_db.mood_snapshots.record(
                happiness=float(self.state.get("happiness", 0) or 0),
                energy=float(self.state.get("energy", 0) or 0),
                curiosity=float(self.state.get("curiosity", 0) or 0),
                fear=float(self.state.get("fear", 0) or 0),
                dominant=self.get_dominant_emotion(),
                ts=now,
            )
            self._last_snapshot_ts = now
        except Exception:
            pass
        
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
        self.state["anger"] = max(0, self.state["anger"] - (decay * 1.5)) # Anger cools down over time
        self._maybe_snapshot()

    def modify(self, mood, delta):
        if mood in self.state:
            self.state[mood] = max(0, min(100, self.state[mood] + delta))
            self._maybe_snapshot()
            
    def get_dominant_emotion(self):
        # Determine the dominant emotion for LEDs / eyes / body language.
        # Order encodes priority: high-arousal negative states win first.
        mood_cfg = self.config.get("defaults", {}).get("mood", {}) if isinstance(self.config.get("defaults"), dict) else {}
        anger_thresh = float(mood_cfg.get("anger_threshold", 45))
        furious_thresh = float(mood_cfg.get("furious_threshold", 75))
        anger = self.state.get("anger", 0)
        if anger > furious_thresh:
            return "furious"
        if self.state["fear"] > 50:
            return "fear"
        if anger > anger_thresh:
            return "anger"
        if self.state["happiness"] > 70:
            return "joy"
        if self.state["happiness"] < 30:
            return "sadness"
        if self.state["curiosity"] > 80:
            return "curiosity"
        if self.state["energy"] < 20:
            return "tired"
        return "neutral"

    def get_body_language_profile(self):
        emotion = self.get_dominant_emotion()
        profiles = (
            self.config.get("defaults", {})
            .get("body_language", {})
            .get("profiles", {})
        )
        profile = profiles.get(emotion) if isinstance(profiles, dict) else None
        if isinstance(profile, dict):
            return profile
        fallback = {
            "joy": {"pan_delta": 6, "tilt_delta": 4, "event": "autonomy.joy"},
            "curiosity": {"pan_delta": 8, "tilt_delta": 3, "event": "autonomy.curious"},
            "fear": {"pan_delta": 10, "tilt_delta": 6, "event": "autonomy.alert"},
            "anger": {"pan_delta": 9, "tilt_delta": 5, "event": "autonomy.angry"},
            "furious": {"pan_delta": 12, "tilt_delta": 7, "event": "autonomy.angry"},
            "tired": {"pan_delta": 2, "tilt_delta": 2, "event": "autonomy.tired"},
            "sadness": {"pan_delta": 3, "tilt_delta": 5, "event": "autonomy.sad"},
            "neutral": {"pan_delta": 4, "tilt_delta": 3, "event": "autonomy.neutral"},
        }
        return fallback.get(emotion, fallback["neutral"])

    def __getitem__(self, key):
        return self.state.get(key)
