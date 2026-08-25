"""Head control arbiter for SentryBOT.

All pan/tilt requests go through this arbiter which enforces:
* Priority ordering (safety > owner > speaker > agent > idle)
* Servo clamping (safe range)
* Rate limiting (max N commands/s)
* Deadband (suppress tiny movements)
* Smooth interpolation
* Source locking (e.g. owner follow lock)
* Duplicate suppression
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("vlm_bridge.head_arbiter")


@dataclass
class HeadCommand:
    pan: float
    tilt: float
    source: str = "autonomy"
    priority: int = 30
    ttl_s: float = 2.0
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at <= 0:
            self.created_at = time.time()

    @property
    def expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_s


try:
    from modules.agent_core.services.action_arbiter import ActionPriority
    _SOURCE_PRIORITY = {
        "manual": int(ActionPriority.MANUAL),
        "safety": int(ActionPriority.SAFETY),
        "owner_follow": int(ActionPriority.OWNER_FOLLOW),
        "active_speaker": int(ActionPriority.ACTIVE_SPEAKER),
        "agent_core": int(ActionPriority.AGENT_TOOL),
        "sound_direction": int(ActionPriority.FRIEND),
        "vlm_interest": int(ActionPriority.VLM_INTEREST),
        "autonomy": int(ActionPriority.AUTONOMY_IDLE),
        "idle": int(ActionPriority.IDLE),
    }
except Exception:
    _SOURCE_PRIORITY = {
        "manual": 100, "safety": 95, "owner_follow": 85,
        "active_speaker": 75, "agent_core": 65, "sound_direction": 60,
        "vlm_interest": 50,
        "autonomy": 30, "idle": 20,
    }


class HeadControlArbiter:
    """Thread-safe head movement arbiter with priority and clamping."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        follow_cfg = cfg.get("follow", cfg)

        self.min_pan = float(follow_cfg.get("min_pan", 35))
        self.max_pan = float(follow_cfg.get("max_pan", 145))
        self.min_tilt = float(follow_cfg.get("min_tilt", 65))
        self.max_tilt = float(follow_cfg.get("max_tilt", 125))
        self.center_pan = float(follow_cfg.get("center_pan", 90))
        self.center_tilt = float(follow_cfg.get("center_tilt", 90))
        self.deadband_deg = float(follow_cfg.get("deadband_deg", 2.0))
        self.smooth_alpha = float(follow_cfg.get("smooth_alpha", 0.5))
        self.max_rate_hz = float(follow_cfg.get("max_rate_hz", 10.0))

        self._lock = threading.Lock()
        self._current_pan = self.center_pan
        self._current_tilt = self.center_tilt
        self._last_cmd_time: float = 0.0
        self._last_pan_sent: float = self.center_pan
        self._last_tilt_sent: float = self.center_tilt
        self._source_lock: Optional[str] = None
        self._source_lock_until: float = 0.0
        self._move_fn: Optional[Callable] = None

    def set_move_callback(self, fn: Callable) -> None:
        self._move_fn = fn

    def request_move(self, cmd: HeadCommand) -> Dict[str, Any]:
        with self._lock:
            return self._evaluate(cmd)

    def move(self, pan: float, tilt: float, source: str = "autonomy", priority: int = 30) -> Dict[str, Any]:
        return self.request_move(HeadCommand(pan=pan, tilt=tilt, source=source, priority=priority))

    def lock_source(self, source: str, duration_s: float = 30.0) -> None:
        with self._lock:
            self._source_lock = source
            self._source_lock_until = time.time() + duration_s

    def unlock(self) -> None:
        with self._lock:
            self._source_lock = None
            self._source_lock_until = 0.0

    @property
    def current_position(self) -> Dict[str, float]:
        with self._lock:
            return {"pan": self._current_pan, "tilt": self._current_tilt}

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pan": self._current_pan, "tilt": self._current_tilt,
                "source_lock": self._source_lock,
                "lock_remaining_s": max(0, self._source_lock_until - time.time()),
            }

    def _evaluate(self, cmd: HeadCommand) -> Dict[str, Any]:
        now = time.time()
        if cmd.expired:
            return {"ok": False, "reason": "expired"}

        # Source lock check
        if self._source_lock and self._source_lock_until > now:
            locked_pri = _SOURCE_PRIORITY.get(self._source_lock, 0)
            cmd_pri = cmd.priority or _SOURCE_PRIORITY.get(cmd.source, 0)
            if cmd_pri < locked_pri and cmd.source != self._source_lock:
                return {"ok": False, "reason": "source_locked", "locked_by": self._source_lock}
        elif self._source_lock and self._source_lock_until <= now:
            self._source_lock = None

        # Rate limit
        min_interval = 1.0 / max(1, self.max_rate_hz)
        if now - self._last_cmd_time < min_interval:
            return {"ok": False, "reason": "rate_limited"}

        # Clamp
        pan = max(self.min_pan, min(self.max_pan, cmd.pan))
        tilt = max(self.min_tilt, min(self.max_tilt, cmd.tilt))

        # Deadband
        if (abs(pan - self._last_pan_sent) < self.deadband_deg and
                abs(tilt - self._last_tilt_sent) < self.deadband_deg):
            return {"ok": False, "reason": "deadband"}

        # Smooth interpolation
        pan = self._current_pan * self.smooth_alpha + pan * (1 - self.smooth_alpha)
        tilt = self._current_tilt * self.smooth_alpha + tilt * (1 - self.smooth_alpha)
        pan = max(self.min_pan, min(self.max_pan, round(pan, 1)))
        tilt = max(self.min_tilt, min(self.max_tilt, round(tilt, 1)))

        # Execute
        self._current_pan = pan
        self._current_tilt = tilt
        self._last_pan_sent = pan
        self._last_tilt_sent = tilt
        self._last_cmd_time = now

        if self._move_fn:
            try:
                self._move_fn(pan, tilt)
            except Exception as exc:
                logger.warning("Head move callback failed: %s", exc)
                return {"ok": False, "reason": "move_error", "error": str(exc)}

        return {"ok": True, "pan": pan, "tilt": tilt}

__all__ = ["HeadControlArbiter", "HeadCommand"]
