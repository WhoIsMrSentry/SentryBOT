"""Companion LED modes: VU-meter strips, jewel thinking ring, center eye, wake spin.

Layout (config-driven): jewel indices + one or two stick segments for stereo VU.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("neopixel.companion")

Color = Tuple[int, int, int]


def _parse_hex_color(raw: Any, default: Color) -> Color:
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        return (int(raw[0]) & 255, int(raw[1]) & 255, int(raw[2]) & 255)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("#") and len(s) >= 7:
            try:
                v = int(s[1:7], 16)
                return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
            except ValueError:
                return default
    return default


def _lerp_color(c1: Color, c2: Color, t: float) -> Color:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _interpolate_gradient(gradient: List[Color], pos: float) -> Color:
    if not gradient:
        return (255, 255, 255)
    if pos <= 0.0:
        return gradient[0]
    if pos >= 1.0:
        return gradient[-1]
    n = len(gradient)
    if n == 1:
        return gradient[0]
    segment = pos * (n - 1)
    idx = int(segment)
    t = segment - idx
    if idx >= n - 1:
        return gradient[-1]
    return _lerp_color(gradient[idx], gradient[idx + 1], t)


class _StickSegment:
    __slots__ = ("start", "count", "channel")

    def __init__(self, start: int, count: int, channel: int = 0) -> None:
        self.start = start
        self.count = count
        self.channel = channel


class CompanionLedController:
    """Background renderer for jewel + stick companion animations."""

    def __init__(self, driver: Any, cfg: Optional[Dict[str, Any]] = None) -> None:
        self._driver = driver
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
                    )
                )
        else:
            stick_start = int(layout.get("stick_start", 7))
            stick_count = int(layout.get("stick_count", max(0, int(getattr(driver, "num_leds", 23)) - 7)))
            half = stick_count // 2
            if half > 0 and stick_count >= 2:
                self._sticks = [
                    _StickSegment(stick_start, half, 0),
                    _StickSegment(stick_start + half, stick_count - half, 1),
                ]
            else:
                self._sticks = [_StickSegment(stick_start, stick_count, 0)]

        colors = self._cfg.get("colors", {}) if isinstance(self._cfg.get("colors"), dict) else {}
        self._thinking_color = _parse_hex_color(colors.get("thinking", "#0066CC"), (0, 102, 204))
        self._eye_color = _parse_hex_color(colors.get("eye_default", "#30E3CA"), (48, 227, 202))
        self._vu_bar = _parse_hex_color(colors.get("vu_bar", "#00AAFF"), (0, 170, 255))
        self._vu_bg = _parse_hex_color(colors.get("vu_bg", "#051018"), (5, 16, 24))
        self._wake_spin_color = _parse_hex_color(colors.get("wake_spin", "#FFD700"), (255, 215, 0))

        vu_gradient_raw = colors.get("vu_gradient")
        if isinstance(vu_gradient_raw, list) and vu_gradient_raw:
            self._vu_gradient = [_parse_hex_color(c, (255, 255, 255)) for c in vu_gradient_raw]
        else:
            self._vu_gradient = [(0, 255, 0), (255, 255, 0), (255, 0, 0)]

        thinking = self._cfg.get("thinking", {}) if isinstance(self._cfg.get("thinking"), dict) else {}
        self._think_step_ms = float(thinking.get("step_ms", 120))
        eye = self._cfg.get("eye", {}) if isinstance(self._cfg.get("eye"), dict) else {}
        self._eye_breathe_ms = float(eye.get("breathe_ms", 800))
        vu = self._cfg.get("vu", {}) if isinstance(self._cfg.get("vu"), dict) else {}
        self._vu_attack = float(vu.get("attack", vu.get("smoothing", 0.75)))
        self._vu_decay = float(vu.get("decay", 0.18))
        self._vu_min = float(vu.get("min_level", 0.04))
        self._tick_ms = float(self._cfg.get("tick_ms", 25))

        wake_spin = self._cfg.get("wake_spin", {}) if isinstance(self._cfg.get("wake_spin"), dict) else {}
        self._wake_spin_duration_ms = float(wake_spin.get("duration_ms", 1200))
        self._wake_spin_wait_ms = float(wake_spin.get("wait_ms", 45))
        self._wake_spin_loops = int(wake_spin.get("loops", 2))
        self._wake_spin_next_mode = str(wake_spin.get("next_mode", "listen_vu")).strip().lower()

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mode = "off"
        self._vu_levels = [0.0, 0.0]
        self._vu_targets = [0.0, 0.0]
        self._think_phase = 0
        self._eye_phase = 0.0
        self._wake_spin_started = 0.0
        self._wake_spin_position = 0
        self._wake_spin_frame_tick = 0

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._mode not in {"", "off"}

    def set_eye_color(self, color: Color) -> None:
        with self._lock:
            self._eye_color = color

    def set_mode(self, mode: str) -> None:
        mode = str(mode or "off").strip().lower()
        with self._lock:
            if mode == self._mode and mode != "wake_spin":
                return
            if self._mode == "wake_spin" and mode in {"listen_vu", "vu", "listen"}:
                return
            self._mode = mode
            self._think_phase = 0
            self._eye_phase = 0.0
            self._wake_spin_position = 0
            self._wake_spin_frame_tick = 0
            if mode == "wake_spin":
                self._wake_spin_started = time.monotonic()
            if mode in {"off", "wake_spin"}:
                self._vu_levels = [0.0, 0.0]
            if mode == "off":
                self._vu_targets = [0.0, 0.0]
        if mode == "off":
            self._clear_companion_range()
            self._maybe_stop_thread()
        else:
            self._ensure_thread()

    def set_vu_level(self, level: float, *, right: Optional[float] = None) -> None:
        level = max(0.0, min(1.0, float(level)))
        if right is None:
            targets = [level, level]
        else:
            targets = [level, max(0.0, min(1.0, float(right)))]
        with self._lock:
            self._vu_targets = targets
            if self._mode == "wake_spin":
                return
            peak = max(targets)
            if self._mode in {"vu", "listen", "listen_vu"}:
                self._mode = "listen_vu"
            elif peak >= self._vu_min:
                self._mode = "listen_vu"
                self._ensure_thread_unlocked()

    def _ensure_thread_unlocked(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="CompanionLeds", daemon=True)
        self._thread.start()

    def _ensure_thread(self) -> None:
        with self._lock:
            self._ensure_thread_unlocked()

    def _maybe_stop_thread(self) -> None:
        with self._lock:
            if self._mode != "off":
                return
        self._stop.set()

    def _loop(self) -> None:
        interval = max(0.015, self._tick_ms / 1000.0)
        while not self._stop.is_set():
            with self._lock:
                mode = self._mode
            if mode == "off":
                break
            try:
                if mode in {"vu", "listen", "listen_vu"}:
                    self._render_vu_frame()
                elif mode == "thinking":
                    self._render_thinking_frame()
                elif mode == "eye":
                    self._render_eye_frame()
                elif mode == "wake_spin":
                    if self._render_wake_spin_frame():
                        with self._lock:
                            self._mode = self._wake_spin_next_mode or "listen_vu"
                elif mode == "wake_chase":
                    self._render_wake_chase_frame()
            except Exception as exc:
                logger.debug("companion frame failed: %s", exc)
            time.sleep(interval)

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
                    self._driver.set(idx, *self._vu_bg)

    def _get_gradient_color(self, position: float) -> Color:
        gradient_colors = self._vu_gradient
        if not gradient_colors or len(gradient_colors) < 2:
            return self._vu_bar
        num_segments = len(gradient_colors) - 1
        segment = min(int(position * num_segments), num_segments - 1)
        segment_t = (position * num_segments) - segment
        return _lerp_color(gradient_colors[segment], gradient_colors[segment + 1], segment_t)

    def _smooth_vu_levels(self) -> List[float]:
        out: List[float] = []
        for idx in range(2):
            current = self._vu_levels[idx]
            target = self._vu_targets[idx]
            rate = self._vu_attack if target >= current else self._vu_decay
            out.append(current + (target - current) * rate)
        self._vu_levels = out
        return out

    def _render_stick_vu(self, stick: _StickSegment, level: float) -> None:
        if level < self._vu_min:
            level = 0.0
        lit = int(round(level * stick.count))
        lit = max(0, min(stick.count, lit))
        for i in range(stick.count):
            idx = stick.start + i
            if idx >= self._driver.num_leds:
                break
            if i < lit:
                pos = i / max(1, stick.count - 1)
                self._driver.set(idx, *_get_gradient_color_safe(self._vu_gradient, self._vu_bar, pos))
            else:
                self._driver.set(idx, *self._vu_bg)

    def _render_vu_frame(self) -> None:
        with self._lock:
            levels = self._smooth_vu_levels()
            eye = self._eye_color
            sticks = list(self._sticks)

        self._clear_sticks()
        for stick in sticks:
            ch = stick.channel if stick.channel in (0, 1) else 0
            self._render_stick_vu(stick, levels[ch])

        self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi))
        er = int(eye[0] * pulse)
        eg = int(eye[1] * pulse)
        eb = int(eye[2] * pulse)
        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                break
            if rel == self._center_rel:
                self._driver.set(idx, er, eg, eb)
            else:
                dim = tuple(int(c * 0.15) for c in eye)
                self._driver.set(idx, *dim)
        self._driver.show()

    def _render_thinking_frame(self) -> None:
        with self._lock:
            self._think_phase = (self._think_phase + 1) % max(1, self._jewel_count - 1)
            phase = self._think_phase
            tc = self._thinking_color
            eye = self._eye_color

        ring_indices = [i for i in range(self._jewel_count) if i != self._center_rel]
        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                continue
            if rel == self._center_rel:
                self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
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
        time.sleep(max(0.02, self._think_step_ms / 1000.0))

    def _render_eye_frame(self) -> None:
        with self._lock:
            eye = self._eye_color
        self._clear_sticks()
        self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi))
        for rel in range(self._jewel_count):
            idx = self._jewel_start + rel
            if idx >= self._driver.num_leds:
                break
            if rel == self._center_rel:
                self._driver.set(idx, int(eye[0] * pulse), int(eye[1] * pulse), int(eye[2] * pulse))
            else:
                dim = tuple(int(c * 0.12) for c in eye)
                self._driver.set(idx, *dim)
        self._driver.show()

    def _render_wake_spin_frame(self) -> bool:
        """Golden RUNNING_LIGHTS on jewel only. Returns True when spin is complete."""
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
        """Legacy wake chase — kept for API compatibility."""
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


def _get_gradient_color_safe(gradient: List[Color], fallback: Color, position: float) -> Color:
    if not gradient or len(gradient) < 2:
        return fallback
    return _interpolate_gradient(gradient, position)
