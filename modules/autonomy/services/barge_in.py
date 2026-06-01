"""Barge-in policy: decide when the user's voice should cut off the robot.

Historically the robot only stopped talking when it heard a wakeword. Natural
conversation also lets you interrupt mid-sentence just by starting to speak.
This controller centralises that decision so it can be unit-tested without any
audio hardware: given (is the robot currently talking?, what did the user say?),
it returns whether to interrupt — with a cooldown so a single utterance doesn't
trigger repeated stops.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class BargeInController:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config if isinstance(config, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        # Wakeword always interrupts; free speech needs at least this many words
        # so coughs / one-word echoes don't constantly cut the robot off.
        self.min_words = int(cfg.get("min_words", 2))
        self.cooldown_s = float(cfg.get("cooldown_s", 1.5))
        self._last_interrupt_ts = 0.0

    def should_interrupt(
        self,
        *,
        robot_speaking: bool,
        user_text: str,
        has_wakeword: bool = False,
        now: Optional[float] = None,
    ) -> bool:
        if not self.enabled:
            return False
        if not robot_speaking:
            return False
        now = time.time() if now is None else now
        if (now - self._last_interrupt_ts) < self.cooldown_s:
            return False
        words = len(str(user_text or "").split())
        if has_wakeword or words >= self.min_words:
            self._last_interrupt_ts = now
            return True
        return False


__all__ = ["BargeInController"]
