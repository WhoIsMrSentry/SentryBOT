"""VLM sampling strategy for SentryBOT.

Decides *when* to trigger a remote VLM call based on events.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("vlm_bridge.vision_sampler")


class VisionSampler:
    """Decides whether a VLM call should be triggered right now."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.min_interval_s = float(cfg.get("min_interval_s", 5.0))
        self.scene_change_threshold = float(cfg.get("scene_change_threshold", 0.35))
        self.max_idle_interval_s = float(cfg.get("max_idle_interval_s", 60.0))
        self.suppress_during_follow = bool(cfg.get("suppress_during_follow", True))
        self._last_call_time: float = 0.0
        self._call_count: int = 0
        self._pending_user_question: bool = False

    def should_call_vlm(
        self, *, new_person: bool = False, owner_seen: bool = False,
        scene_change_score: float = 0.0, user_question: bool = False,
        hazard_detected: bool = False, sudden_motion: bool = False,
        is_bored: bool = False, follow_mode_active: bool = False,
    ) -> bool:
        now = time.time()
        elapsed = now - self._last_call_time
        mandatory = user_question or hazard_detected or self._pending_user_question

        if not mandatory and elapsed < self.min_interval_s:
            return False
        if follow_mode_active and self.suppress_during_follow and not mandatory:
            return False
        if user_question or self._pending_user_question:
            self._pending_user_question = False
            return True
        if hazard_detected:
            return True
        if owner_seen and elapsed > self.min_interval_s:
            return True
        if new_person and elapsed > self.min_interval_s:
            return True
        if sudden_motion and elapsed > self.min_interval_s * 1.5:
            return True
        if scene_change_score >= self.scene_change_threshold and elapsed > self.min_interval_s:
            return True
        if is_bored and elapsed > self.max_idle_interval_s:
            return True
        if elapsed > self.max_idle_interval_s * 2:
            return True
        return False

    def request_user_question(self) -> None:
        self._pending_user_question = True

    def record_call(self) -> None:
        self._last_call_time = time.time()
        self._call_count += 1

    @property
    def time_since_last_call(self) -> float:
        if self._last_call_time <= 0:
            return float("inf")
        return time.time() - self._last_call_time

    def get_stats(self) -> Dict[str, Any]:
        return {
            "call_count": self._call_count,
            "time_since_last_s": round(self.time_since_last_call, 1),
            "pending_user_question": self._pending_user_question,
        }

__all__ = ["VisionSampler"]
