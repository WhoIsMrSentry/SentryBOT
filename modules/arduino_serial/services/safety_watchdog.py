"""Hardware & Software Safety Watchdog for Arduino and Actuators.

Implements a Dead-Man's Switch and link liveness monitor:
- Continuously checks heartbeat and ACK liveness between the Host and Arduino.
- If serial communication halts or firmware freezes while robot is active/in-motion,
  automatically triggers Emergency Stop (ESTOP), centers servos, and notifies StateStore.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("arduino_serial.safety_watchdog")


class HardwareSafetyWatchdog:
    """Monitors communication liveness and dispatches ESTOP if connection is lost."""

    def __init__(
        self,
        timeout_s: float = 2.5,
        check_interval_s: float = 0.5,
        on_estop_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.timeout_s = max(0.05, float(timeout_s))
        self.check_interval_s = max(0.01, float(check_interval_s))
        self.on_estop_callback = on_estop_callback

        self._lock = threading.RLock()
        self._last_feed_ts: float = time.time()
        self._is_tripped: bool = False
        self._trip_reason: str = ""
        self._is_moving: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_feed_ts = time.time()
            self._is_tripped = False
            self._thread = threading.Thread(
                target=self._watchdog_loop,
                name="SentryBOT-SafetyWatchdog",
                daemon=True,
            )
            self._thread.start()
            logger.info("HardwareSafetyWatchdog started (timeout=%.1fs)", self.timeout_s)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def feed(self, source: str = "hb") -> None:
        """Feed the watchdog to refresh link liveness timestamp."""
        with self._lock:
            self._last_feed_ts = time.time()

    def set_motion_state(self, is_moving: bool) -> None:
        with self._lock:
            self._is_moving = bool(is_moving)
            if self._is_moving:
                self._last_feed_ts = time.time()

    def reset_trip(self) -> bool:
        """Re-arm the watchdog after an emergency stop condition is cleared."""
        with self._lock:
            self._is_tripped = False
            self._trip_reason = ""
            self._last_feed_ts = time.time()
            logger.info("HardwareSafetyWatchdog re-armed.")
            return True

    def _trigger_estop(self, reason: str) -> None:
        with self._lock:
            if self._is_tripped:
                return
            self._is_tripped = True
            self._trip_reason = reason
        logger.error("SAFETY WATCHDOG TRIPPED: %s -> Triggering emergency stop", reason)
        if self.on_estop_callback is not None:
            try:
                self.on_estop_callback(reason)
            except Exception as exc:
                logger.error("Error executing safety watchdog on_estop_callback: %s", exc)

    def _watchdog_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.check_interval_s)
            now = time.time()
            with self._lock:
                elapsed = now - self._last_feed_ts
                tripped = self._is_tripped
                moving = self._is_moving

            if not tripped and elapsed > self.timeout_s:
                reason = f"Watchdog timeout: no heartbeat received for {elapsed:.2f}s (threshold={self.timeout_s:.1f}s)"
                self._trigger_estop(reason)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self._last_feed_ts
            return {
                "active": self._thread is not None and self._thread.is_alive(),
                "tripped": self._is_tripped,
                "trip_reason": self._trip_reason,
                "timeout_s": self.timeout_s,
                "time_since_last_feed_s": round(elapsed, 3),
                "is_moving": self._is_moving,
            }


__all__ = ["HardwareSafetyWatchdog"]
