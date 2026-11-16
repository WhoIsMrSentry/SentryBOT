"""Head Control Arbiter Integration for Arduino Serial Transport.

This module provides transport-level enforcement of HeadControlArbiter
for all head movement commands (track, set_pose with pan/tilt).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("arduino_serial.head_arbiter_integration")


@dataclass
class HeadMovementResult:
    """Result of head movement arbitration."""
    allowed: bool
    pan: Optional[float] = None
    tilt: Optional[float] = None
    reason: Optional[str] = None
    original_pan: Optional[float] = None
    original_tilt: Optional[float] = None


class HeadArbiterTransportWrapper:
    """Wrapper that enforces HeadControlArbiter for head movement commands."""

    def __init__(
        self,
        head_arbiter: Any,
        enable: bool = True,
        bypass_for_testing: bool = False,
    ):
        self.head_arbiter = head_arbiter
        self.enable = enable
        self.bypass_for_testing = bypass_for_testing
        self._lock = threading.Lock()

        # Track commands that require head arbiter
        self._HEAD_COMMANDS = frozenset({"track", "set_pose"})
        # set_servo on the pan/tilt indices is also a head move; ear/other
        # indices stay ungated (R2: no servo bypass channels).
        self._PAN_INDEX = 0
        self._TILT_INDEX = 1
        # Last-known pose axes; center (90) until the first gated move so
        # single-axis set_servo calls always carry a complete pan/tilt pair.
        self._last_pan: Optional[float] = 90.0
        self._last_tilt: Optional[float] = 90.0

    def is_head_command(self, command: Dict[str, Any]) -> bool:
        """Check if command requires head arbiter."""
        cmd = command.get("cmd")
        if cmd == "set_servo":
            try:
                return int(command.get("index", -1)) in (self._PAN_INDEX, self._TILT_INDEX)
            except (TypeError, ValueError):
                return False
        if cmd not in self._HEAD_COMMANDS:
            return False
        if cmd == "set_pose":
            pose = command.get("pose", [])
            return len(pose) >= 2
        return True

    def extract_pan_tilt(self, command: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        """Extract pan/tilt from command, preserving valid 0.0 coordinates."""
        cmd = command.get("cmd")
        if cmd == "set_servo":
            try:
                index = int(command.get("index", -1))
                deg = float(command.get("deg", 90.0))
            except (TypeError, ValueError):
                return None, None
            with self._lock:
                if index == self._PAN_INDEX:
                    return deg, self._last_tilt
                if index == self._TILT_INDEX:
                    return self._last_pan, deg
            return None, None
        if cmd == "track":
            raw_pan = command["pan"] if command.get("pan") is not None else command.get("head_pan")
            raw_tilt = command["tilt"] if command.get("tilt") is not None else command.get("head_tilt")
            try:
                pan = float(raw_pan) if raw_pan is not None else None
                tilt = float(raw_tilt) if raw_tilt is not None else None
            except (TypeError, ValueError):
                return None, None
            with self._lock:
                if pan is None:
                    pan = self._last_pan
                if tilt is None:
                    tilt = self._last_tilt
            return pan, tilt
        if cmd == "set_pose":
            pose = command.get("pose", [])
            if len(pose) >= 2:
                try:
                    return float(pose[0]), float(pose[1])
                except (TypeError, ValueError):
                    return None, None
        return None, None

    def check_and_wrap(self, command: Dict[str, Any], source: str = "autonomy") -> "HeadMovementResult":
        """Check command against HeadControlArbiter and return fail-closed result on errors."""
        if not self.enable or self.head_arbiter is None:
            return HeadMovementResult(allowed=True)

        if self.bypass_for_testing:
            return HeadMovementResult(allowed=True)

        if not self.is_head_command(command):
            return HeadMovementResult(allowed=True)

        pan, tilt = self.extract_pan_tilt(command)
        if pan is None or tilt is None:
            return HeadMovementResult(allowed=True)

        original_pan, original_tilt = pan, tilt
        priority_map = {
            "safety": 95,
            "owner_follow": 85,
            "active_speaker": 75,
            "agent_core": 65,
            "sound_direction": 60,
            "vlm_interest": 50,
            "vlm_bridge": 50,
            "autonomy": 30,
            "animate": 90,
            "speech": 60,
            "idle": 20,
        }
        priority = priority_map.get(source, 30)

        try:
            result = self.head_arbiter.move(pan=pan, tilt=tilt, source=source, priority=priority)
            if not isinstance(result, dict) or not result.get("ok", False):
                reason = result.get("reason", "arbiter_denied") if isinstance(result, dict) else "arbiter_denied"
                return HeadMovementResult(
                    allowed=False,
                    original_pan=original_pan,
                    original_tilt=original_tilt,
                    reason=str(reason),
                )

            final_pan = result.get("pan", pan)
            final_tilt = result.get("tilt", tilt)
            with self._lock:
                if final_pan is not None:
                    self._last_pan = float(final_pan)
                if final_tilt is not None:
                    self._last_tilt = float(final_tilt)
            return HeadMovementResult(
                allowed=True,
                pan=final_pan,
                tilt=final_tilt,
                original_pan=original_pan,
                original_tilt=original_tilt,
            )
        except Exception as exc:
            logger.warning("Head arbiter error, denying command (fail-closed): %s", exc)
            return HeadMovementResult(
                allowed=False,
                original_pan=original_pan,
                original_tilt=original_tilt,
                reason=f"arbiter_error:{exc}",
            )

    def wrap_command(self, command: Dict[str, Any], source: str = "autonomy") -> Dict[str, Any]:
        """Wrap command with arbiter checks and return potentially modified command."""
        result = self.check_and_wrap(command, source)

        if not result.allowed:
            raise RuntimeError(
                f"Head movement denied by arbiter: {result.reason} "
                f"(source={source}, pan={result.original_pan}, tilt={result.original_tilt})"
            )

        if result.pan is not None or result.tilt is not None:
            modified = dict(command)
            if command.get("cmd") == "track":
                if result.pan is not None:
                    modified["pan"] = result.pan
                    modified["head_pan"] = result.pan
                if result.tilt is not None:
                    modified["tilt"] = result.tilt
                    modified["head_tilt"] = result.tilt
            elif command.get("cmd") == "set_pose":
                pose = list(modified.get("pose", []))
                if result.pan is not None and len(pose) > 0:
                    pose[0] = result.pan
                if result.tilt is not None and len(pose) > 1:
                    pose[1] = result.tilt
                modified["pose"] = pose
            elif command.get("cmd") == "set_servo":
                index = int(command.get("index", -1))
                if index == self._PAN_INDEX and result.pan is not None:
                    modified["deg"] = float(result.pan)
                elif index == self._TILT_INDEX and result.tilt is not None:
                    modified["deg"] = float(result.tilt)
            return modified

        return command