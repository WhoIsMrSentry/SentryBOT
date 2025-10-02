from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

try:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
except Exception:
    from ..arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore

from .config_loader import load_config

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


class xAnimateService:
    """YAML tabanlı servo animasyon yürütücüsü.

    Şema (örnek):
    name: sit
    loop: false
    steps:
      - pose: [90,110,60, 90,110,60, 90,90]
        duration_ms: 1200
      - pose: [90,110,60, 90,110,60, 90,90]
        hold_ms: 500
    """

    def __init__(self, serial: Optional[xArduinoSerialService] = None, config_overrides: Optional[Dict[str, Any]] = None):
        self.cfg = load_config(overrides=config_overrides)
        self.serial = serial or xArduinoSerialService()
        self._running = False

    def start(self) -> None:
        self.serial.start()

    def stop(self) -> None:
        self.serial.stop()

    # API
    def list(self) -> List[str]:
        base = self.cfg["animations_dir"]
        out: List[str] = []
        for fn in os.listdir(base):
            if fn.lower().endswith((".yml", ".yaml")):
                out.append(os.path.splitext(fn)[0])
        return sorted(out)

    def load(self, name: str) -> Dict[str, Any]:
        path = self._resolve_path(name)
        if yaml is None:
            raise RuntimeError("PyYAML missing")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict) or "steps" not in data:
            raise ValueError("invalid animation file")
        return data

    def run(self, name: str, speed: float | None = None, loop: Optional[bool] = None) -> None:
        anim = self.load(name)
        speed_mul = speed if speed is not None else float(self.cfg.get("default_speed", 1.0))
        do_loop = bool(anim.get("loop", False) if loop is None else loop)
        self._running = True
        try:
            while self._running:
                for step in anim.get("steps", []):
                    if not self._running:
                        break
                    pose: List[int] = list(step.get("pose", []))
                    dur_ms: int = int(step.get("duration_ms", 0))
                    hold_ms: int = int(step.get("hold_ms", 0))
                    if dur_ms > 0:
                        dur_ms = max(1, int(dur_ms / max(0.01, speed_mul)))
                    # send pose
                    if pose:
                        self.serial.set_pose(pose, duration_ms=dur_ms if dur_ms > 0 else None)
                    # hold
                    if hold_ms > 0:
                        time.sleep(max(0.0, hold_ms / 1000.0))
                if not do_loop:
                    break
        finally:
            self._running = False

    def stop_run(self) -> None:
        self._running = False

    # utils
    def _resolve_path(self, name: str) -> str:
        base = self.cfg["animations_dir"]
        for ext in (".yml", ".yaml"):
            p = os.path.join(base, name + ext)
            if os.path.exists(p):
                return p
        raise FileNotFoundError(name)
