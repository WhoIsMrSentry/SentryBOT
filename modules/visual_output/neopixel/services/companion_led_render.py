from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List, Mapping, Tuple

from .companion_led_helpers import Color, _StickSegment, _parse_hex_color

logger = logging.getLogger("neopixel.companion_render")


class CompanionLedRenderMixin:
    """Frame renderers for jewel and stick brows."""

    _driver: Any
    _sticks: List[_StickSegment]
    _jewel_start: int
    _jewel_count: int
    _center_rel: int
    _stick_off: Color
    _lock: Any
    _think_phase: int
    _thinking_color: Color
    _eye_color: Color
    _eye_phase: float
    _tick_ms: float
    _eye_breathe_ms: float
    _think_step_ms: float
    _face_frame: Dict[str, Any]
    _face_frame_expires_at: float
    _face_profiles: Dict[str, Any]
    _mode: str
    _wake_spin_started: float
    _wake_spin_duration_ms: float
    _wake_spin_color: Color
    _wake_spin_position: int
    _wake_spin_wait_ms: float
    _wake_spin_frame_tick: int

    @staticmethod
    def _bounded(value: Any, default: float) -> float:
        raise NotImplementedError

    def _companion_indices(self) -> range:
        end = self._jewel_start + self._jewel_count
        for stick in self._sticks:
            end = max(end, stick.start + stick.count)
        return range(self._jewel_start, min(end, self._driver.num_leds))

    def _clear_companion_range(self) -> None:
        for i in self._companion_indices():
            self._driver.set(i, 0, 0, 0)
        self._driver.show()

    def _clear_sticks(self) -> None:
        for stick in self._sticks:
            for i in range(stick.count):
                idx = stick.start + i
                if idx < self._driver.num_leds:
                    self._driver.set(idx, *self._stick_off)

    def _render_thinking_frame(self) -> None:
        with self._lock:
            now = time.monotonic()
            step_s = max(0.02, self._think_step_ms / 1000.0)
            if (now - self._think_last_advance) >= step_s:
                self._think_phase = (self._think_phase + 1) % max(1, self._jewel_count - 1)
                self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
                self._think_last_advance = now
            phase = self._think_phase
            tc = self._thinking_color
            eye = self._eye_color

        ring_indices = [i for i in range(self._jewel_count) if i != self._center_rel]
        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                continue
            if rel == self._center_rel:
                pulse = 0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi)
                self._driver.set(
                    idx,
                    int(eye[0] * pulse),
                    int(eye[1] * pulse),
                    int(eye[2] * pulse),
                )
                continue
            ring_pos = ring_indices.index(rel) if rel in ring_indices else 0
            on = (ring_pos + phase) % 2 == 0
            if on:
                self._driver.set(idx, *tc)
            else:
                self._driver.set(idx, int(tc[0] * 0.08), int(tc[1] * 0.08), int(tc[2] * 0.12))

        self._clear_sticks()
        for stick in self._sticks:
            for i in range(stick.count):
                idx = stick.start + i
                if idx >= self._driver.num_leds:
                    break
                fade = 0.12 + 0.08 * math.sin((self._eye_phase + i * 0.2) * math.pi)
                self._driver.set(idx, int(tc[0] * fade), int(tc[1] * fade), int(tc[2] * fade))
        self._driver.show()

    def _render_eye_frame(self) -> None:
        with self._lock:
            eye = self._eye_color

        self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi))

        opp = (255 - eye[0], 255 - eye[1], 255 - eye[2])

        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                break
            if rel == self._center_rel:
                self._driver.set(idx, int(opp[0] * pulse), int(opp[1] * pulse), int(opp[2] * pulse))
            else:
                self._driver.set(idx, int(eye[0] * 0.15), int(eye[1] * 0.15), int(eye[2] * 0.15))

        eyebrow_pulse = 0.2 + 0.5 * (0.5 + 0.5 * math.cos(self._eye_phase * math.pi))
        for stick in self._sticks:
            for i in range(stick.count):
                idx = stick.start + i
                if idx >= self._driver.num_leds:
                    break
                arch_factor = math.sin((i / max(1, stick.count - 1)) * math.pi)
                intensity = eyebrow_pulse * (0.4 + 0.6 * arch_factor)
                self._driver.set(idx, int(eye[0] * intensity), int(eye[1] * intensity), int(eye[2] * intensity))

        self._driver.show()

    def _render_face_frame(self) -> None:
        with self._lock:
            frame = dict(self._face_frame)
            expired = bool(frame) and time.monotonic() >= self._face_frame_expires_at
            if expired:
                self._face_frame = {}
                self._mode = "eye"
        if not frame or expired:
            self._render_eye_frame()
            return
        eye = frame.get("eye", {})
        eye_color = _parse_hex_color(eye.get("color"), self._eye_color)
        eye_brightness = self._bounded(eye.get("brightness", 0.75), 0.75)
        pulse_hz = max(0.0, float(eye.get("pulse_hz", 0.0) or 0.0))
        pulse = 1.0 if pulse_hz <= 0.0 else 0.70 + 0.30 * (0.5 + 0.5 * math.sin(time.monotonic() * pulse_hz * 2.0 * math.pi))
        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                break
            level = eye_brightness * pulse
            self._driver.set(idx, int(eye_color[0] * level), int(eye_color[1] * level), int(eye_color[2] * level))
        brows = frame.get("brows", {})
        for stick in self._sticks:
            spec = brows.get(stick.name, {}) if isinstance(brows, Mapping) else {}
            pose = str(spec.get("pose") or "neutral")
            profile = self._face_profiles.get(pose, self._face_profiles.get("neutral", {}))
            if not isinstance(profile, Mapping):
                profile = {}
            color = _parse_hex_color(spec.get("color"), eye_color)
            intensity = self._bounded(spec.get("intensity", profile.get("intensity", 0.65)), 0.65)
            slope = float(profile.get("slope", 0.0) or 0.0)
            arch = self._bounded(profile.get("arch", 0.0), 0.0)
            phase = self._bounded(spec.get("phase", profile.get("phase", 0.0)), 0.0)
            for physical_rel in range(stick.count):
                idx = stick.start + physical_rel
                if idx >= self._driver.num_leds:
                    break
                logical_rel = (stick.count - 1 - physical_rel) if stick.reverse else physical_rel
                progress = logical_rel / max(1, stick.count - 1)
                arch_factor = 1.0 - arch + arch * math.sin(progress * math.pi)
                level = self._bounded(intensity + slope * (progress - 0.5), intensity) * arch_factor
                level *= 0.82 + 0.18 * math.sin((time.monotonic() + phase) * 2.0 * math.pi)
                self._driver.set(idx, int(color[0] * level), int(color[1] * level), int(color[2] * level))
        self._driver.show()

    def _render_wake_spin_frame(self) -> bool:
        with self._lock:
            started = self._wake_spin_started
            duration_s = self._wake_spin_duration_ms / 1000.0
            color = self._wake_spin_color
            position = self._wake_spin_position

        if (time.monotonic() - started) >= duration_s:
            self._clear_sticks()
            return True

        self._clear_sticks()
        r, g, b = color
        n = self._jewel_count
        steps_per_advance = max(1, int(self._wake_spin_wait_ms / max(1.0, self._tick_ms)))
        with self._lock:
            self._wake_spin_frame_tick += 1
            if self._wake_spin_frame_tick >= steps_per_advance:
                self._wake_spin_frame_tick = 0
                position += 1
                self._wake_spin_position = position
            else:
                position = self._wake_spin_position
        for rel in range(n):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                continue
            sin_val = math.sin((rel + position) * 1.0) * 127 + 128
            ratio = sin_val / 255.0
            self._driver.set(idx, int(r * ratio), int(g * ratio), int(b * ratio))
        self._driver.show()
        return False

    def _render_wake_chase_frame(self) -> None:
        with self._lock:
            eye = self._eye_color

        self._clear_sticks()
        self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi))
        center_idx = self._jewel_start + self._center_rel
        if center_idx < self._driver.num_leds:
            self._driver.set(center_idx, int(eye[0] * pulse), int(eye[1] * pulse), int(eye[2] * pulse))
        for rel in range(1, self._jewel_count):
            idx = self._jewel_start + rel
            if idx < self._driver.num_leds:
                dim = tuple(int(c * 0.2) for c in eye)
                self._driver.set(idx, *dim)
        self._driver.show()
