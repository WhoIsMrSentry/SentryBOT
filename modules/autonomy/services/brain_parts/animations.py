"""Head animation helpers for AutonomyBrain."""
from __future__ import annotations

import random
import time


class AnimationSupportMixin:
    """Provides reusable micro-movements and animation fallbacks."""

    def _perform_micro_movement(self) -> None:
        """Subtle servo movements to simulate breathing/aliveness."""
        profile = {}
        if hasattr(self, "mood") and hasattr(self.mood, "get_body_language_profile"):
            profile = self.mood.get_body_language_profile() or {}
        pan_delta = max(1, int(profile.get("pan_delta", 4)))
        tilt_delta = max(1, int(profile.get("tilt_delta", 3)))

        center_pan = int(self.state.get("current_pan", 90))
        center_tilt = int(self.state.get("current_tilt", 90))
        target_pan = max(45, min(135, center_pan + random.randint(-pan_delta, pan_delta)))
        target_tilt = max(65, min(125, center_tilt + random.randint(-tilt_delta, tilt_delta)))

        self.state["current_pan"] = target_pan
        self.state["current_tilt"] = target_tilt
        self.client.move_head(target_pan, target_tilt)

        evt = profile.get("event")
        if isinstance(evt, str) and evt and random.random() < 0.18:
            self.client.push_interaction_event(evt)

        # Layer subtle eye + ear life on top of head motion for richer liveliness.
        if random.random() < 0.25:
            self._perform_eye_saccade()
        if random.random() < 0.2:
            self._perform_ear_micromovement()

    def _perform_eye_saccade(self) -> None:
        """Briefly dart the eyes to a random gaze direction."""
        gaze = random.choice(["look_left", "look_right", "look_up", "look_down"])
        try:
            self.client.oled_show(gaze)
        except Exception:
            pass

    def _perform_ear_micromovement(self) -> None:
        """Nudge the ears toward the current mood pose for ambient liveliness."""
        dominant = "neutral"
        if hasattr(self, "mood") and hasattr(self.mood, "get_dominant_emotion"):
            try:
                dominant = self.mood.get_dominant_emotion() or "neutral"
            except Exception:
                dominant = "neutral"
        try:
            self.client.push_interaction_event(f"emotion:{dominant}")
        except Exception:
            pass

    def _trigger_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> bool:
        resp = self.client.run_animation(name, speed=speed, loop=loop)
        return bool(resp and resp.get("ok"))

    def _head_scan_fallback(self) -> None:
        pan = random.randint(60, 120)
        tilt = random.randint(70, 110)
        self.state["current_pan"] = pan
        self.state["current_tilt"] = tilt
        self.client.move_head(pan, tilt)

    def _stretch_fallback(self) -> None:
        self.client.move_head(45, 130)
        time.sleep(1)
        self.client.move_head(135, 130)
        time.sleep(1)
        self.client.move_head(90, 90)

    def _blink_fallback(self) -> None:
        self.client.push_interaction_event("autonomy.blink")

    def _perform_owner_scan(self) -> None:
        sweep = [60, 120, 90]
        for pan in sweep:
            self.client.move_head(pan, self.state["current_tilt"])
            time.sleep(0.2)
