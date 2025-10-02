from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Dict

logger = logging.getLogger("speech.pan_tilt")


@dataclass
class PanTiltConfig:
    enabled: bool = False
    center_deg: float = 90.0
    min_deg: float = 0.0
    max_deg: float = 180.0
    slew_deg_per_s: float = 120.0
    update_hz: float = 20.0


class PanTiltController:
    """Minimal pan controller with slew limiting and callback sender.

    sender: Callable[[float], None] is invoked with absolute pan angle (deg).
    Default sender logs; replace with hardware integration (e.g., serial or API).
    """

    def __init__(self, cfg: Dict, sender: Optional[Callable[[float], None]] = None):
        self.cfg = PanTiltConfig(
            enabled=bool(cfg.get("enabled", False)),
            center_deg=float(cfg.get("center_deg", 90.0)),
            min_deg=float(cfg.get("min_deg", 0.0)),
            max_deg=float(cfg.get("max_deg", 180.0)),
            slew_deg_per_s=float(cfg.get("slew_deg_per_s", 120.0)),
            update_hz=float(cfg.get("update_hz", 20.0)),
        )
        self._sender = sender or (lambda ang: logger.info("pan-> %.1f deg", ang))
        self._target = self.cfg.center_deg
        self._current = self.cfg.center_deg
        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._active = False

    def start(self):
        if self._active:
            return
        self._stop.clear()
        self._active = True
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        self._active = False

    def set_target(self, angle_deg: float):
        # clamp
        angle = max(self.cfg.min_deg, min(self.cfg.max_deg, angle_deg))
        self._target = angle

    def status(self) -> Dict:
        return {
            "active": self._active,
            "current": self._current,
            "target": self._target,
            "min": self.cfg.min_deg,
            "max": self.cfg.max_deg,
        }

    def _run(self):
        dt = 1.0 / max(1.0, self.cfg.update_hz)
        max_slew = self.cfg.slew_deg_per_s
        last = time.time()
        while not self._stop.is_set():
            now = time.time()
            dt = max(1e-3, now - last)
            last = now
            max_step = max_slew * dt if max_slew > 0 else float('inf')
            err = self._target - self._current
            if abs(err) > 1e-3:
                step = max(-max_step, min(max_step, err))
                self._current += step
                self._sender(self._current)
            time.sleep(1.0 / max(1.0, self.cfg.update_hz))
