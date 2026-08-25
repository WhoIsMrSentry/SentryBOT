"""Companion LED modes: jewel thinking ring, center eye, face, wake spin.

Layout (config-driven): jewel indices + stick segments for brows.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .companion_led_helpers import (
    Color,
    _StickSegment,
    _parse_hex_color,
    _lerp_color,
    _interpolate_gradient,
)
from .companion_led_render import CompanionLedRenderMixin

logger = logging.getLogger("neopixel.companion")


class CompanionLedController(CompanionLedRenderMixin):
    """Background renderer for jewel + stick companion animations."""

    VALID_MODES = {"off", "listen", "thinking", "eye", "face", "wake_spin", "wake_chase"}

    def __init__(
        self,
        driver: Any,
        cfg: Optional[Dict[str, Any]] = None,
        frame_lock: Optional[threading.RLock] = None,
    ) -> None:
        self._driver = driver
        self._frame_lock = frame_lock or threading.RLock()
        self._cfg = cfg if isinstance(cfg, dict) else {}
        layout = self._cfg.get("layout", {}) if isinstance(self._cfg.get("layout"), dict) else {}
        self._jewel_start = int(layout.get("jewel_start", 0))
        self._jewel_count = int(layout.get("jewel_count", 7))
        self._center_rel = int(layout.get("jewel_center_index", 0))

        sticks_raw = layout.get("sticks")
        if isinstance(sticks_raw, list) and sticks_raw:
            self._sticks: List[_StickSegment] = []
            for item in sticks_raw:
                if not isinstance(item, dict):
                    continue
                self._sticks.append(
                    _StickSegment(
                        int(item.get("start", 0)),
                        int(item.get("count", 0)),
                        int(item.get("channel", 0)),
                        str(item.get("name") or ("left_brow" if len(self._sticks) == 0 else "right_brow")),
                        bool(item.get("reverse", False)),
                    )
                )
        else:
            stick_start = int(layout.get("stick_start", 7))
            stick_count = int(layout.get("stick_count", max(0, int(getattr(driver, "num_leds", 23)) - 7)))
            half = stick_count // 2
            if half > 0 and stick_count >= 2:
                self._sticks = [
                    _StickSegment(stick_start, half, 0, "left_brow"),
                    _StickSegment(stick_start + half, stick_count - half, 1, "right_brow"),
                ]
            else:
                self._sticks = [_StickSegment(stick_start, stick_count, 0, "left_brow")]

        colors = self._cfg.get("colors", {}) if isinstance(self._cfg.get("colors"), dict) else {}
        self._thinking_color = _parse_hex_color(colors.get("thinking", "#0066CC"), (0, 102, 204))
        self._eye_color = _parse_hex_color(colors.get("eye_default", "#30E3CA"), (48, 227, 202))
        face_cfg = self._cfg.get("face", {}) if isinstance(self._cfg.get("face"), dict) else {}
        self._face_default_duration_ms = max(100, int(face_cfg.get("default_duration_ms", 1400)))
        self._face_profiles = face_cfg.get("pose_profiles", {}) if isinstance(face_cfg.get("pose_profiles"), dict) else {}
        self._semantic_catalog = face_cfg.get("semantics", {}) if isinstance(face_cfg.get("semantics"), dict) else {}
        self._face_frame: Dict[str, Any] = {}
        self._face_frame_expires_at = 0.0
        self._stick_off = _parse_hex_color(colors.get("stick_off", "#000000"), (0, 0, 0))
        self._wake_spin_color = _parse_hex_color(colors.get("wake_spin", "#FFD700"), (255, 215, 0))

        thinking = self._cfg.get("thinking", {}) if isinstance(self._cfg.get("thinking"), dict) else {}
        self._think_step_ms = float(thinking.get("step_ms", 120))
        eye = self._cfg.get("eye", {}) if isinstance(self._cfg.get("eye"), dict) else {}
        self._eye_breathe_ms = float(eye.get("breathe_ms", 800))
        self._tick_ms = float(self._cfg.get("tick_ms", 25))

        wake_spin = self._cfg.get("wake_spin", {}) if isinstance(self._cfg.get("wake_spin"), dict) else {}
        self._wake_spin_duration_ms = float(wake_spin.get("duration_ms", 1200))
        self._wake_spin_wait_ms = float(wake_spin.get("wait_ms", 45))
        self._wake_spin_loops = int(wake_spin.get("loops", 2))
        self._wake_spin_next_mode = str(wake_spin.get("next_mode", "eye")).strip().lower()

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mode = "off"
        self._think_phase = 0
        self._think_last_advance = 0.0
        self._eye_phase = 0.0
        self._wake_spin_started = 0.0
        self._wake_spin_position = 0
        self._wake_spin_frame_tick = 0
        self._pending_mode = ""

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._mode not in {"", "off"}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self._mode,
                "pending_mode": self._pending_mode,
                "renderer_alive": bool(self._thread and self._thread.is_alive()),
            }

    def set_eye_color(self, color: Color) -> None:
        with self._lock:
            self._eye_color = color

    @staticmethod
    def _bounded(value: Any, default: float) -> float:
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return default

    def semantic_catalog(self) -> Dict[str, Any]:
        return {name: dict(value) for name, value in self._semantic_catalog.items() if isinstance(value, Mapping)}

    def apply_semantic(self, semantic: str, *, revision: str = "", duration_ms: Optional[int] = None) -> bool:
        entry = self._semantic_catalog.get(str(semantic or "").strip())
        if not isinstance(entry, Mapping):
            logger.warning("unknown companion semantic ignored: %s", semantic)
            return False
        raw_frame = entry.get("frame", {})
        frame: Dict[str, Any] = dict(raw_frame) if isinstance(raw_frame, Mapping) else {}
        frame["semantic"] = str(semantic)
        frame["revision"] = str(revision or "")
        configured_duration = entry.get("duration_ms")
        active_duration = duration_ms if duration_ms is not None else configured_duration
        return self.apply_face_frame(frame, duration_ms=active_duration)

    def apply_face_frame(self, frame: Mapping[str, Any], *, duration_ms: Optional[int] = None) -> bool:
        if not isinstance(frame, Mapping):
            logger.warning("invalid face frame ignored")
            return False
        with self._lock:
            self._face_frame = self._normalize_face_frame(frame)
            requested_ms = duration_ms if duration_ms is not None else frame.get("duration_ms")
            try:
                active_ms = max(100, int(requested_ms)) if requested_ms is not None else self._face_default_duration_ms
            except (TypeError, ValueError):
                active_ms = self._face_default_duration_ms
            self._face_frame_expires_at = time.monotonic() + (active_ms / 1000.0)
        return self.set_mode("face")

    def _normalize_face_frame(self, frame: Mapping[str, Any]) -> Dict[str, Any]:
        eye_raw = frame.get("eye", {})
        if not isinstance(eye_raw, Mapping):
            eye_raw = {}
        eye_color = _parse_hex_color(eye_raw.get("color"), self._eye_color)
        brows: Dict[str, Dict[str, Any]] = {}
        for stick in self._sticks:
            raw = frame.get(stick.name, {})
            if not isinstance(raw, Mapping):
                raw = {}
            pose = str(raw.get("pose") or "neutral").strip().lower()
            profile = self._face_profiles.get(pose, {})
            if not isinstance(profile, Mapping):
                profile = {}
            brows[stick.name] = {
                "pose": pose,
                "color": _parse_hex_color(raw.get("color", profile.get("color", eye_color)), eye_color),
                "intensity": self._bounded(raw.get("intensity", profile.get("intensity", 0.65)), 0.65),
                "phase": self._bounded(raw.get("phase", profile.get("phase", 0.0)), 0.0),
            }
        return {
            "semantic": str(frame.get("semantic") or "ambient_idle"),
            "revision": str(frame.get("revision") or ""),
            "eye": {
                "color": eye_color,
                "brightness": self._bounded(eye_raw.get("brightness", 0.75), 0.75),
                "pulse_hz": max(0.0, float(eye_raw.get("pulse_hz", 0.0) or 0.0)),
            },
            "brows": brows,
        }

    def set_mode(self, mode: str) -> bool:
        mode = str(mode or "off").strip().lower()
        aliases = {"vu": "listen", "listen_vu": "listen", "": "off"}
        mode = aliases.get(mode, mode)
        if mode not in self.VALID_MODES:
            logger.warning("unknown companion mode ignored: %s", mode)
            return False
        with self._lock:
            if mode == self._mode and mode != "wake_spin":
                return True
            if self._mode == "wake_spin" and mode not in {"off", "wake_spin"}:
                self._pending_mode = mode
                return True
            self._mode = mode
            self._think_phase = 0
            self._think_last_advance = 0.0
            self._eye_phase = 0.0
            self._wake_spin_position = 0
            self._wake_spin_frame_tick = 0
            if mode == "wake_spin":
                self._wake_spin_started = time.monotonic()
                self._pending_mode = ""
            if mode == "off":
                self._pending_mode = ""
        if mode == "off":
            with self._frame_lock:
                self._clear_companion_range()
        else:
            self._ensure_thread()
        return True

    def stop(self) -> None:
        self.set_mode("off")
        self._stop.set()

    def _ensure_thread_unlocked(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="CompanionLeds", daemon=True)
        self._thread.start()

    def _ensure_thread(self) -> None:
        with self._lock:
            self._ensure_thread_unlocked()

    def _loop(self) -> None:
        interval = max(0.015, self._tick_ms / 1000.0)
        while not self._stop.is_set():
            with self._lock:
                mode = self._mode
            if mode == "off":
                self._stop.wait(interval)
                continue
            try:
                with self._frame_lock:
                    if mode in {"listen", "eye"}:
                        self._render_eye_frame()
                    elif mode == "thinking":
                        self._render_thinking_frame()
                    elif mode == "face":
                        self._render_face_frame()
                    elif mode == "wake_spin":
                        if self._render_wake_spin_frame():
                            self._complete_wake_spin()
                    elif mode == "wake_chase":
                        self._render_wake_chase_frame()
            except Exception as exc:
                logger.debug("companion frame failed: %s", exc)
            self._stop.wait(interval)

    def _complete_wake_spin(self) -> None:
        with self._lock:
            self._mode = self._pending_mode or self._wake_spin_next_mode or "eye"
            self._pending_mode = ""
