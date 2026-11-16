from __future__ import annotations

import logging
import math
import threading
from typing import Any, Dict, Optional, Tuple

try:
    from .driver import Servo, ServoConfig, create_pi_gpio_backend
    from .ears import gesture_sound, gesture_wakeword, pose_for_emotion
    from .ear_reflex import EarReflexEngine
except ImportError:
    from driver import Servo, ServoConfig, create_pi_gpio_backend  # type: ignore
    from ears import gesture_sound, gesture_wakeword, pose_for_emotion  # type: ignore
    from ear_reflex import EarReflexEngine  # type: ignore

logger = logging.getLogger("piservo.runner")


class EarRunner:
    def __init__(
        self,
        left_cfg: ServoConfig,
        right_cfg: ServoConfig,
        *,
        shared_backend: Optional[Any] = None,
        smooth_enabled: bool = True,
        ramp_hz: float = 50.0,
        max_speed_deg_s: float = 360.0,
        idle_detach_ms: int = 800,
    ):
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._return_timer: Optional[threading.Timer] = None
        self._idle_timer: Optional[threading.Timer] = None

        self._smooth_enabled = bool(smooth_enabled)
        self._ramp_hz = max(10.0, min(100.0, float(ramp_hz)))
        self._max_speed_deg_s = max(0.0, float(max_speed_deg_s))
        self._idle_detach_ms = max(0, int(idle_detach_ms))
        self._closed = False

        # Share ONE GPIO backend across both ears unless per-servo Arduino backend is configured
        self._shared_backend: Optional[Any] = shared_backend
        if self._shared_backend is None and left_cfg.arduino_index is None and right_cfg.arduino_index is None:
            self._shared_backend = create_pi_gpio_backend()

        self.left = Servo(
            left_cfg,
            backend=self._shared_backend if left_cfg.arduino_index is None else None,
        )
        self.right = Servo(
            right_cfg,
            backend=self._shared_backend if right_cfg.arduino_index is None else None,
        )

        center_l = float(left_cfg.center_deg)
        center_r = float(right_cfg.center_deg)
        self.ear_reflex = EarReflexEngine(neutral_left=center_l, neutral_right=center_r)

        self._cur_left = center_l
        self._cur_right = center_r
        self._tgt_left = center_l
        self._tgt_right = center_r

        self._ramp_thread: Optional[threading.Thread] = None
        if self._smooth_enabled and self._max_speed_deg_s > 0.0:
            self._ramp_thread = threading.Thread(
                target=self._ramp_loop,
                daemon=True,
                name="piservo-ramp",
            )
            self._ramp_thread.start()

        # Start safely centered at configured neutral angle
        self.set_angles(center_l, center_r, immediate=True)

    @property
    def backend_name(self) -> str:
        l_name = self.left.backend_name
        r_name = self.right.backend_name
        return l_name if l_name == r_name else f"{l_name}/{r_name}"

    @property
    def last_error(self) -> Optional[str]:
        return self.left.last_error or self.right.last_error

    def is_healthy(self) -> bool:
        return (not self._closed) and (self.last_error is None)

    @staticmethod
    def _clamp(cfg: ServoConfig, angle: float) -> float:
        return max(float(cfg.min_deg), min(float(cfg.max_deg), float(angle)))

    def _cancel_return_timer(self) -> None:
        if self._return_timer is not None:
            self._return_timer.cancel()
            self._return_timer = None

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _schedule_idle_detach(self) -> None:
        self._cancel_idle_timer()
        if self._closed or self._idle_detach_ms <= 0:
            return
        timer = threading.Timer(self._idle_detach_ms / 1000.0, self._on_idle_detach)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _on_idle_detach(self) -> None:
        with self._lock:
            if self._closed:
                return
            if (
                abs(self._tgt_left - self._cur_left) <= 0.1
                and abs(self._tgt_right - self._cur_right) <= 0.1
            ):
                self.left.detach()
                self.right.detach()

    def _schedule_return_to_center(self, delay_s: float) -> None:
        self._cancel_return_timer()
        if self._closed or delay_s <= 0:
            return
        timer = threading.Timer(delay_s, self._on_return_center)
        timer.daemon = True
        self._return_timer = timer
        timer.start()

    def _on_return_center(self) -> None:
        self._move_to(
            float(self.left.cfg.center_deg),
            float(self.right.cfg.center_deg),
            cancel_return=False,
        )

    def _ramp_loop(self) -> None:
        dt = 1.0 / self._ramp_hz
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=1.0)
            self._wake_event.clear()
            while not self._stop_event.is_set():
                with self._lock:
                    dl = self._tgt_left - self._cur_left
                    dr = self._tgt_right - self._cur_right
                    max_step = self._max_speed_deg_s * dt
                    if abs(dl) <= 0.5 and abs(dr) <= 0.5:
                        if dl != 0.0 or dr != 0.0 or not self.left.pwm_active:
                            self._cur_left = self._tgt_left
                            self._cur_right = self._tgt_right
                            self.left.set_angle(self._cur_left)
                            self.right.set_angle(self._cur_right)
                        self._schedule_idle_detach()
                        break
                    step_l = max(-max_step, min(max_step, dl))
                    step_r = max(-max_step, min(max_step, dr))
                    self._cur_left += step_l
                    self._cur_right += step_r
                    self.left.set_angle(self._cur_left)
                    self.right.set_angle(self._cur_right)
                if self._stop_event.wait(timeout=dt):
                    return

    def _move_to(
        self,
        left: float,
        right: float,
        *,
        immediate: bool = False,
        cancel_return: bool = True,
    ) -> Tuple[float, float]:
        clamped_l = self._clamp(self.left.cfg, left)
        clamped_r = self._clamp(self.right.cfg, right)
        with self._lock:
            if cancel_return:
                self._cancel_return_timer()
            self._cancel_idle_timer()
            self._tgt_left = clamped_l
            self._tgt_right = clamped_r

            use_immediate = (
                immediate
                or (not self._smooth_enabled)
                or (self._max_speed_deg_s <= 0.0)
                or (abs(clamped_l - self._cur_left) <= 1.0 and abs(clamped_r - self._cur_right) <= 1.0)
            )
            if use_immediate:
                self._cur_left = clamped_l
                self._cur_right = clamped_r
                self.left.set_angle(clamped_l)
                self.right.set_angle(clamped_r)
                self._schedule_idle_detach()
            else:
                self._wake_event.set()
            return (clamped_l, clamped_r)

    def set_angles(self, left: float, right: float, *, immediate: bool = False) -> Tuple[float, float]:
        return self._move_to(left, right, immediate=immediate, cancel_return=True)

    def reflex(self, angle: float, energy: float = 1.0) -> Tuple[float, float]:
        with self._lock:
            angles = self.ear_reflex.compute_reflex(angle, energy)
            if angles is None:
                return (self._tgt_left, self._tgt_right)
            return self.set_angles(angles.left, angles.right)

    def emotion(self, name: str) -> Tuple[float, float]:
        pose = pose_for_emotion(name)
        return self.set_angles(pose.left, pose.right)

    def gesture(self, name: str) -> Tuple[float, float]:
        n = str(name or "").strip().lower()
        if n == "wakeword":
            left_deg, right_deg = gesture_wakeword()
            res = self.set_angles(left_deg, right_deg)
            self._schedule_return_to_center(0.2)
            return res
        if n == "sound":
            left_deg, right_deg = gesture_sound()
            res = self.set_angles(left_deg, right_deg)
            self._schedule_return_to_center(0.3)
            return res
        if n == "vigilance":
            left_deg, right_deg = self.ear_reflex.compute_vigilance()
            return self.set_angles(left_deg, right_deg)
        if n in ("relax", "idle"):
            left_deg, right_deg = self.ear_reflex.compute_relax()
            return self.set_angles(left_deg, right_deg)
        raise ValueError(f"unknown gesture: {name}")

    def event(self, kind: str) -> Tuple[float, float]:
        k = str(kind or "").strip().lower()
        if k.startswith("doa:") or k.startswith("sound:"):
            try:
                angle = float(k.split(":", 1)[1])
            except (ValueError, IndexError) as exc:
                raise ValueError(f"invalid doa/sound event: {kind}") from exc
            if not math.isfinite(angle):
                raise ValueError(f"non-finite doa/sound angle: {kind}")
            return self.reflex(angle)
        return self.gesture(kind)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": self.is_healthy(),
                "backend": self.backend_name,
                "error": self.last_error,
                "left": round(self._cur_left, 2),
                "right": round(self._cur_right, 2),
                "target_left": round(self._tgt_left, 2),
                "target_right": round(self._tgt_right, 2),
                "pwm_active": bool(self.left.pwm_active or self.right.pwm_active),
                "smooth_enabled": self._smooth_enabled,
                "idle_detach_ms": self._idle_detach_ms,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel_return_timer()
            self._cancel_idle_timer()
        self._stop_event.set()
        self._wake_event.set()
        if self._ramp_thread is not None and self._ramp_thread.is_alive():
            self._ramp_thread.join(timeout=1.0)
        with self._lock:
            self.left.close()
            self.right.close()
            if self._shared_backend is not None and hasattr(self._shared_backend, "close"):
                self._shared_backend.close()
