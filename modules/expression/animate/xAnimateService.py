from __future__ import annotations

import logging
import math
import os
import threading
from typing import Any, Dict, List, Optional

try:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.contract import SERVO_COUNT  # type: ignore
except ImportError:  # pragma: no cover
    xArduinoSerialService = None  # type: ignore
    SERVO_COUNT = 4  # type: ignore

from .config_loader import load_config
from .services.procedural_motion import ProceduralMotionEngine

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger("animate")


def _clamp_deg(value: Any, default: int = 90) -> int:
    try:
        return max(0, min(180, int(value)))
    except Exception:
        return int(default)


def _safe_nonneg_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


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
        serial: Optional[Any] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        ears: Any = None,
    ):
        self.cfg = load_config(overrides=config_overrides)
        self._owns_serial = serial is None
        if serial is not None:
            self.serial = serial
        else:
            if xArduinoSerialService is None:
                raise RuntimeError(
                    "xArduinoSerialService is unavailable; pass serial or install arduino_serial dependencies"
                )
            self.serial = xArduinoSerialService()

        self._ears = ears
        self._oled = None
        self._neopixel = None

        self._run_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._active_thread: Optional[threading.Thread] = None

        self._running = False
        self._active_name: Optional[str] = None
        self._step_index: int = -1
        self._total_steps: int = 0
        self._looping: bool = False
        self._degraded: bool = False

        rest = list(self.cfg.get("rest_pose") or [90, 90, 90, 90])
        while len(rest) < SERVO_COUNT:
            rest.append(90)
        self._rest = [_clamp_deg(v) for v in rest[:SERVO_COUNT]]

        ear_center = (self._rest[2] + self._rest[3]) / 2.0 if len(self._rest) >= 4 else 90.0
        self._idle_engine = ProceduralMotionEngine(
            base_pan=float(self._rest[0]),
            base_tilt=float(self._rest[1]),
            breathing_period_s=float(self.cfg.get("idle_breathing_period_s", 4.5)),
            tilt_amplitude_deg=float(self.cfg.get("idle_tilt_amp_deg", 1.8)),
            ear_center_deg=float(ear_center),
            ear_amplitude_deg=float(self.cfg.get("idle_ear_amp_deg", 1.5)),
        )

    def attach_ears(self, ears: Any) -> None:
        self._ears = ears

    def attach_oled(self, oled: Any) -> None:
        self._oled = oled

    def attach_neopixel(self, neopixel: Any) -> None:
        self._neopixel = neopixel

    def start(self) -> None:
        if self.serial is None:
            raise RuntimeError("serial backend is not configured")
        self.serial.start()

    def stop(self) -> None:
        self.stop_run(return_to_rest=False)
        if self._owns_serial and self.serial is not None:
            self.serial.stop()

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "ok": True,
                "running": bool(self._running),
                "name": self._active_name,
                "step_index": self._step_index,
                "total_steps": self._total_steps,
                "loop": self._looping,
                "degraded": self._degraded,
            }

    def sample_idle_pose(self, current_time_s: Optional[float] = None) -> Dict[str, Any]:
        """Compute one subtle breathing/ear micro-drift sample using configured rest centers."""
        return self._idle_engine.compute_motion(current_time_s=current_time_s)

    def step_idle(self, current_time_s: Optional[float] = None) -> Dict[str, Any]:
        """Apply a procedural breathing pose only when no script animation is active."""
        with self._state_lock:
            if self._running:
                return {}
        sample = self.sample_idle_pose(current_time_s=current_time_s)
        pose: List[Optional[int]] = [
            _clamp_deg(sample["pan"]),
            _clamp_deg(sample["tilt"]),
            _clamp_deg(sample["ears"]["left"]),
            _clamp_deg(sample["ears"]["right"]),
        ]
        try:
            self._apply_pose(pose, None)
        except Exception as exc:
            logger.debug("animate idle step skipped: %s", exc)
        return sample

    # API
    def list(self) -> List[str]:
        base = self.cfg["animations_dir"]
        if not os.path.isdir(base):
            return []
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
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
            raise ValueError("invalid animation file")
        return data

    def start_async(
        self,
        name: str,
        speed: float | None = None,
        loop: Optional[bool] = None,
    ) -> threading.Thread:
        """Validate animation before spawning a background playback thread."""
        anim = self.load(name)
        speed_mul = self._validate_speed(speed)
        do_loop = bool(anim.get("loop", False) if loop is None else loop)

        # Cancel any currently running animation and wait for its lock release cleanly.
        self.stop_run(return_to_rest=False)
        started = threading.Event()
        t = threading.Thread(
            target=self._execute_loaded,
            args=(name, anim, speed_mul, do_loop, started),
            daemon=True,
            name=f"animate-{name}",
        )
        with self._state_lock:
            self._active_thread = t
        t.start()
        started.wait(timeout=0.5)
        return t

    def run(self, name: str, speed: float | None = None, loop: Optional[bool] = None) -> bool:
        anim = self.load(name)
        speed_mul = self._validate_speed(speed)
        do_loop = bool(anim.get("loop", False) if loop is None else loop)
        # Ensure any previous background run yields before acquiring _run_lock.
        self.stop_run(return_to_rest=False)
        return self._execute_loaded(name, anim, speed_mul, do_loop)

    def _validate_speed(self, speed: float | None) -> float:
        speed_mul = float(speed if speed is not None else self.cfg.get("default_speed", 1.0))
        if not math.isfinite(speed_mul) or speed_mul <= 0.0:
            raise ValueError("speed must be a finite number > 0")
        return max(0.05, min(10.0, speed_mul))

    def _execute_loaded(
        self,
        name: str,
        anim: Dict[str, Any],
        speed_mul: float,
        do_loop: bool,
        started: Optional[threading.Event] = None,
    ) -> bool:
        steps = list(anim.get("steps") or [])
        interpolate = bool(self.cfg.get("interpolate", True))

        with self._run_lock:
            self._stop_event.clear()
            with self._state_lock:
                self._running = True
                self._active_name = name
                self._step_index = 0
                self._total_steps = len(steps)
                self._looping = do_loop
                self._degraded = False
            if started is not None:
                started.set()

            degraded = False
            try:
                while not self._stop_event.is_set():
                    for idx, step in enumerate(steps):
                        if self._stop_event.is_set():
                            break
                        if not isinstance(step, dict):
                            continue
                        with self._state_lock:
                            self._step_index = idx

                        pose = self._normalize_pose(list(step.get("pose") or []))
                        dur_ms = _safe_nonneg_int(step.get("duration_ms"), 0)
                        hold_ms = _safe_nonneg_int(step.get("hold_ms"), 0)
                        if dur_ms > 0:
                            dur_ms = max(1, int(round(dur_ms / speed_mul)))
                        if hold_ms > 0:
                            hold_ms = max(1, int(round(hold_ms / speed_mul)))

                        if pose:
                            try:
                                pose_dur = dur_ms if (interpolate and dur_ms > 0) else None
                                self._apply_pose(pose, pose_dur)
                            except Exception as exc:
                                logger.warning("animate degraded: pose step skipped (%s)", exc)
                                degraded = True
                                self._stop_event.set()
                                break

                        face = step.get("face") or step.get("eyes")
                        if face and self._oled is not None:
                            self._apply_oled(face)

                        led = step.get("led") or step.get("neopixel")
                        if led and self._neopixel is not None:
                            self._apply_neopixel(led)

                        # Interruptible step pacing across move duration + explicit hold
                        wait_ms = (dur_ms if interpolate else 0) + hold_ms
                        if wait_ms > 0:
                            if self._stop_event.wait(timeout=wait_ms / 1000.0):
                                break

                    if not do_loop or self._stop_event.is_set():
                        break
            finally:
                with self._state_lock:
                    self._running = False
                    self._degraded = degraded
                    if not degraded:
                        self._step_index = -1
                        self._active_name = None
                        self._looping = False
                    if self._active_thread is threading.current_thread():
                        self._active_thread = None
            return not degraded

    def _apply_oled(self, face: Any) -> None:
        try:
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

    def _apply_neopixel(self, led: Any) -> None:
        try:
            if isinstance(led, (list, tuple)) and len(led) == 3:
                self._neopixel.fill(int(led[0]), int(led[1]), int(led[2]))
            elif isinstance(led, str):
                if hasattr(self._neopixel, "companion_set_mode"):
                    self._neopixel.companion_set_mode(led)
                elif hasattr(self._neopixel, "set_mode"):
                    self._neopixel.set_mode(led)
                else:
                    logger.debug("animate neopixel attach target has no mode API")
        except Exception as exc:
            logger.debug("animate neopixel step skipped: %s", exc)

    def stop_run(self, return_to_rest: bool = False) -> None:
        self._stop_event.set()
        with self._state_lock:
            self._running = False
            thread = self._active_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        if return_to_rest:
            with self._run_lock:
                try:
                    dur = 400 if self.cfg.get("interpolate", True) else None
                    self._apply_pose(list(self._rest), duration_ms=dur)
                except Exception as exc:
                    logger.warning("animate return_to_rest failed: %s", exc)

    # utils
    def _resolve_path(self, name: str) -> str:
        clean = str(name or "").strip()
        if (
            not clean
            or "\x00" in clean
            or "/" in clean
            or "\\" in clean
            or ".." in clean
        ):
            raise ValueError(f"invalid animation name: {name!r}")

        base = os.path.realpath(self.cfg["animations_dir"])
        for ext in (".yml", ".yaml"):
            candidate = os.path.realpath(os.path.join(base, clean + ext))
            if not (candidate == base or candidate.startswith(base + os.sep)):
                raise ValueError(f"invalid animation path: {name!r}")
            if os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError(clean)

    def _apply_pose(self, pose: List[Optional[int]], duration_ms: Optional[int]) -> None:
        if self.serial is None:
            raise RuntimeError("serial backend unavailable")
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
            try:
                self._ears.set_angles(float(values[2]), float(values[3]))
            except Exception as exc:
                logger.debug("animate ears step skipped: %s", exc)

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
