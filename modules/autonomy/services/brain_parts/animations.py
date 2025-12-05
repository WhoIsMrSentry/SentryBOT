"""Head animation helpers for AutonomyBrain."""
from __future__ import annotations

import random
import time


class AnimationSupportMixin:
    """Provides reusable micro-movements and animation fallbacks."""

    def _perform_micro_movement(self) -> None:
        """Subtle servo movements to simulate breathing/aliveness."""
        delta_tilt = random.randint(-2, 2)
        target_tilt = 90 + delta_tilt
        self.state["current_tilt"] = target_tilt
        self.client.move_head(self.state["current_pan"], target_tilt)

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
