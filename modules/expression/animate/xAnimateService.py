from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

try:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.contract import (  # type: ignore
        SERVO_COUNT,
    )
except Exception:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.contract import (  # type: ignore
        SERVO_COUNT,
    )

from .config_loader import load_config

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

logger = logging.getLogger("animate")


def _clamp_deg(value: Any, default: int = 90) -> int:
    try:
        return max(0, min(180, int(value)))
    except Exception:
        return int(default)


class xAnimateService:
    """YAML tabanlı servo animasyon yürütücüsü.

    Şema (örnek):
    name: sit
    loop: false
    steps:
      - pose: [90, 90, 90, 90]  # pan, tilt, ear_l, ear_r
        duration_ms: 1200
      - pose: [90, 90]          # 2 values: ears use rest_pose
        hold_ms: 500
    """

    def __init__(
        self,
        serial: Optional[xArduinoSerialService] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        ears: Any = None,
    ):
        self.cfg = load_config(overrides=config_overrides)
        self.serial = serial or xArduinoSerialService()
        self._ears = ears
        self._oled = None
        self._neopixel = None
        self._running = False
        rest = list(self.cfg.get("rest_pose") or [90, 90, 90, 90])
        while len(rest) < SERVO_COUNT:
            rest.append(90)
        self._rest = [_clamp_deg(v) for v in rest[:SERVO_COUNT]]

    def attach_ears(self, ears: Any) -> None:
        self._ears = ears

    def attach_oled(self, oled: Any) -> None:
        self._oled = oled

    def attach_neopixel(self, neopixel: Any) -> None:
        self._neopixel = neopixel

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

    def run(self, name: str, speed: float | None = None, loop: Optional[bool] = None) -> bool:
        anim = self.load(name)
        speed_mul = speed if speed is not None else float(self.cfg.get("default_speed", 1.0))
        do_loop = bool(anim.get("loop", False) if loop is None else loop)
        self._running = True
        degraded = False
        try:
            while self._running:
                for step in anim.get("steps", []):
                    if not self._running:
                        break
                    pose_raw: List[Any] = list(step.get("pose", []))
                    pose = self._normalize_pose(pose_raw)
                    dur_ms: int = int(step.get("duration_ms", 0))
                    hold_ms: int = int(step.get("hold_ms", 0))
                    if dur_ms > 0:
                        dur_ms = max(1, int(dur_ms / max(0.01, speed_mul)))
                    if pose:
                        try:
                            self._apply_pose(pose, dur_ms if dur_ms > 0 else None)
                        except Exception as exc:
                            logger.warning("animate degraded: pose step skipped (%s)", exc)
                            degraded = True
                            self._running = False
                            break
                    face = step.get("face") or step.get("eyes")
                    if face and self._oled is not None:
                        try:
                            # Real OLED service surface: xOledFacesService
                            # exposes apply_manual()/on_interaction_event()
                            # (NOT on_event/on_mode - those never existed and
                            # silently skipped every face step, R27).
                            if hasattr(self._oled, "apply_manual"):
                                self._oled.apply_manual("animation", str(face))
                            elif hasattr(self._oled, "on_interaction_event"):
                                self._oled.on_interaction_event("animate.face", {"emotion": str(face)})
                            elif hasattr(self._oled, "on_event"):
                                self._oled.on_event(str(face), {})
                            elif hasattr(self._oled, "on_mode"):
                                self._oled.on_mode(str(face))
                            else:
                                logger.debug("animate oled attach target has no known face API")
                        except Exception as exc:
                            logger.debug("animate oled step skipped: %s", exc)
                    led = step.get("led") or step.get("neopixel")
                    if led and self._neopixel is not None:
                        try:
                            if isinstance(led, (list, tuple)) and len(led) == 3:
                                self._neopixel.fill(int(led[0]), int(led[1]), int(led[2]))
                            elif isinstance(led, str):
                                # NeoRunner exposes companion_set_mode(); plain
                                # set_mode only exists on CompanionLeds.
                                if hasattr(self._neopixel, "companion_set_mode"):
                                    self._neopixel.companion_set_mode(led)
                                elif hasattr(self._neopixel, "set_mode"):
                                    self._neopixel.set_mode(led)
                                else:
                                    logger.debug("animate neopixel attach target has no mode API")
                        except Exception as exc:
                            logger.debug("animate neopixel step skipped: %s", exc)
                    # hold
                    if hold_ms > 0:
                        time.sleep(max(0.0, hold_ms / 1000.0))
                if not do_loop:
                    break
        finally:
            self._running = False
        return not degraded

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

    def _apply_pose(self, pose: List[Optional[int]], duration_ms: Optional[int]) -> None:
        if len(pose) >= 2 and (len(pose) < 4 or (pose[2] is None and pose[3] is None)):
            if pose[0] is not None:
                self.serial.set_servo(0, float(pose[0]), source="animate")
            if pose[1] is not None:
                self.serial.set_servo(1, float(pose[1]), source="animate")
            return

        values = [self._rest[i] if v is None else int(v) for i, v in enumerate(pose)]
        while len(values) < SERVO_COUNT:
            values.append(self._rest[len(values)])
        self.serial.set_pose(values[:SERVO_COUNT], duration_ms=duration_ms, source="animate")
        if self._ears is not None and hasattr(self._ears, "set_angles"):
            self._ears.set_angles(float(values[2]), float(values[3]))

    def _normalize_pose(self, pose: List[Any]) -> List[Optional[int]]:
        """Normalize animation pose to 4 channels: [pan, tilt, ear_l, ear_r]."""
        if not pose:
            return []
        n = len(pose)
        if n == 2:
            return [
                xAnimateService._opt_deg(pose[0]),
                xAnimateService._opt_deg(pose[1]),
                None,
                None,
            ]
        if n == SERVO_COUNT:
            return [xAnimateService._opt_deg(v) for v in pose]
        if n == 8:
            return [
                xAnimateService._opt_deg(pose[7]),
                xAnimateService._opt_deg(pose[6]),
                None,
                None,
            ]
        return []

    @staticmethod
    def _opt_deg(value: Any) -> Optional[int]:
        if value is None:
            return None
        return _clamp_deg(value)
