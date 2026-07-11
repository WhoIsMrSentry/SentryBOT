"""Companion LED modes: VU-meter strip, jewel thinking ring, center eye, wake chase.

Layout (config-driven, default): indices 0-6 = NeoPixel Jewel (0 = center eye),
indices 7+ = straight strip for audio level display.
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
    """Linear interpolation between two colors."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _interpolate_gradient(gradient: List[Color], pos: float) -> Color:
    """Interpolate color from gradient at position pos (0.0 to 1.0)."""
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


class CompanionLedController:
    """Background renderer for jewel + stick companion animations."""

    def __init__(self, driver: Any, cfg: Optional[Dict[str, Any]] = None) -> None:
        self._driver = driver
        self._cfg = cfg if isinstance(cfg, dict) else {}
        layout = self._cfg.get("layout", {}) if isinstance(self._cfg.get("layout"), dict) else {}
        self._jewel_start = int(layout.get("jewel_start", 0))
        self._jewel_count = int(layout.get("jewel_count", 7))
        self._center_rel = int(layout.get("jewel_center_index", 0))
        self._stick_start = int(layout.get("stick_start", 7))
        self._stick_count = int(layout.get("stick_count", max(0, int(getattr(driver, "num_leds", 23)) - 7)))

        colors = self._cfg.get("colors", {}) if isinstance(self._cfg.get("colors"), dict) else {}
        self._thinking_color = _parse_hex_color(colors.get("thinking", "#0066CC"), (0, 102, 204))
        self._eye_color = _parse_hex_color(colors.get("eye_default", "#30E3CA"), (48, 227, 202))
        self._vu_bar = _parse_hex_color(colors.get("vu_bar", "#00AAFF"), (0, 170, 255))
        self._vu_bg = _parse_hex_color(colors.get("vu_bg", "#051018"), (5, 16, 24))

        # VU gradient colors (green -> yellow -> red)
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
        self._vu_smoothing = float(vu.get("smoothing", 0.35))
        self._vu_min = float(vu.get("min_level", 0.04))
        self._tick_ms = float(self._cfg.get("tick_ms", 50))

        # Wake chase config
        wake_chase = self._cfg.get("wake_chase", {}) if isinstance(self._cfg.get("wake_chase"), dict) else {}
        self._wake_chase_speed_ms = float(wake_chase.get("speed_ms", 80))
        self._wake_chase_direction_cw = bool(wake_chase.get("direction_cw", True))
        self._wake_chase_pair_gap = int(wake_chase.get("pair_gap", 1))

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mode = "off"
        self._vu_level = 0.0
        self._vu_target = 0.0
        self._think_phase = 0
        self._eye_phase = 0.0
        
        # Wake chase state
        self._wake_chase_phase = 0
        self._wake_chase_direction = 1  # 1 for CW, -1 for CCW
        self._wake_chase_tick = 0

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_eye_color(self, color: Color) -> None:
        with self._lock:
            self._eye_color = color

    def set_mode(self, mode: str) -> None:
        mode = str(mode or "off").strip().lower()
        with self._lock:
            if mode == self._mode:
                return
            self._mode = mode
            self._think_phase = 0
            self._eye_phase = 0.0
            self._wake_chase_phase = 0
            self._wake_chase_tick = 0
            if mode == "off":
                self._vu_level = 0.0
                self._vu_target = 0.0
        if mode == "off":
            self._clear_companion_range()
            self._maybe_stop_thread()
        else:
            self._ensure_thread()

    def set_vu_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        with self._lock:
            self._vu_target = level
            if self._mode in {"vu", "listen"}:
                self._mode = "vu"

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="CompanionLeds", daemon=True)
        self._thread.start()

    def _maybe_stop_thread(self) -> None:
        with self._lock:
            if self._mode != "off":
                return
        self._stop.set()

    def _loop(self) -> None:
        interval = max(0.02, self._tick_ms / 1000.0)
        while not self._stop.is_set():
            with self._lock:
                mode = self._mode
            if mode == "off":
                break
            try:
                if mode in {"vu", "listen"}:
                    self._render_vu_frame()
                elif mode == "thinking":
                    self._render_thinking_frame()
                elif mode == "eye":
                    self._render_eye_frame()
                elif mode == "wake_chase":
                    self._render_wake_chase_frame()
            except Exception as exc:
                logger.debug("companion frame failed: %s", exc)
            time.sleep(interval)

    def _clear_companion_range(self) -> None:
        end = self._stick_start + self._stick_count
        for i in range(self._jewel_start, min(end, self._driver.num_leds)):
            self._driver.set(i, 0, 0, 0)
        self._driver.show()

    def _lerp_color(self, c1: Color, c2: Color, t: float) -> Color:
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def _get_gradient_color(self, position: float) -> Color:
        """Get color from vu_gradient based on position (0.0 - 1.0)."""
        with self._lock:
            gradient_colors = getattr(self, '_vu_gradient', None)
            if not gradient_colors or len(gradient_colors) < 2:
                return self._vu_bar
        
        # Find which segment of the gradient we're in
        num_segments = len(gradient_colors) - 1
        segment = min(int(position * num_segments), num_segments - 1)
        segment_t = (position * num_segments) - segment
        
        c1 = gradient_colors[segment]
        c2 = gradient_colors[segment + 1]
        return self._lerp_color(c1, c2, segment_t)

    def _render_vu_frame(self) -> None:
        with self._lock:
            self._vu_level += (self._vu_target - self._vu_level) * self._vu_smoothing
            level = self._vu_level
            eye = self._eye_color

        # Stick VU meter with gradient colors
        lit = int(round(level * self._stick_count))
        lit = max(0, min(self._stick_count, lit))
        for i in range(self._stick_count):
            idx = self._stick_start + i
            if idx >= self._driver.num_leds:
                break
            if i < lit:
                # Use gradient color based on position in the lit portion
                if lit > 0:
                    pos = i / max(1, lit - 1) if lit > 1 else 0.5
                else:
                    pos = 0.0
                color = self._get_gradient_color(pos)
                self._driver.set(idx, *color)
            else:
                self._driver.set(idx, *self._vu_bg)

        # Jewel ring dim + center eye pulse while listening
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
            # Opposing / alternating pattern on jewel ring (1 on, 1 off, rotating)
            ring_pos = ring_indices.index(rel) if rel in ring_indices else 0
            on = (ring_pos + phase) % 2 == 0
            if on:
                self._driver.set(idx, *tc)
            else:
                self._driver.set(idx, int(tc[0] * 0.08), int(tc[1] * 0.08), int(tc[2] * 0.12))

        # Stick: subtle blue breathe while thinking
        for i in range(self._stick_count):
            idx = self._stick_start + i
            if idx >= self._driver.num_leds:
                break
            fade = 0.12 + 0.08 * math.sin((self._eye_phase + i * 0.2) * math.pi)
            self._driver.set(idx, int(tc[0] * fade), int(tc[1] * fade), int(tc[2] * fade))
        self._driver.show()
        time.sleep(max(0.02, self._think_step_ms / 1000.0))

    def _render_eye_frame(self) -> None:
        with self._lock:
            eye = self._eye_color
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

    def _render_wake_chase_frame(self) -> None:
        """Wake word chase animation on jewel ring (indices 1-6).
        
        Ring has 6 LEDs (1-6): 3 top (1,2,3) and 3 bottom (4,5,6).
        Opposite pairs: (1,4), (2,5), (3,6) chase each other.
        Direction alternates CW/CCB based on config.
        Center (index 0) pulses subtly.
        """
        with self._lock:
            eye = self._eye_color
            chase_color = eye  # Use eye color for chase
            speed_ms = self._wake_chase_speed_ms
            direction_cw = self._wake_chase_direction_cw
            pair_gap = self._wake_chase_pair_gap

        # Determine direction (can be toggled externally if needed)
        self._wake_chase_tick += 1
        
        # Update phase based on speed
        if self._wake_chase_tick >= max(1, int(speed_ms / self._tick_ms)):
            self._wake_chase_tick = 0
            self._wake_chase_phase = (self._wake_chase_phase + (1 if direction_cw else -1)) % 6

        # Ring LED indices (relative to jewel_start): 1,2,3,4,5,6
        # Opposite pairs: (1,4), (2,5), (3,6)
        pairs = [(1, 4), (2, 5), (3, 6)]
        
        # Center eye pulse
        self._eye_phase += self._tick_ms / max(200.0, self._eye_breathe_ms)
        pulse = 0.3 + 0.4 * (0.5 + 0.5 * math.sin(self._eye_phase * 2 * math.pi))
        center_idx = self._jewel_start + self._center_rel
        if center_idx < self._driver.num_leds:
            self._driver.set(center_idx, 
                           int(eye[0] * pulse), 
                           int(eye[1] * pulse), 
                           int(eye[2] * pulse))

        # Chase animation on pairs
        for pair_idx, (top, bottom) in enumerate(pairs):
            # Each pair activates in sequence with a gap
            active_pair = (self._wake_chase_phase // (pair_gap + 1)) % len(pairs)
            is_active = (pair_idx == active_pair)
            
            if is_active:
                # Active pair: both LEDs on (bright)
                for rel in (top, bottom):
                    idx = self._jewel_start + rel
                    if idx < self._driver.num_leds:
                        self._driver.set(idx, *chase_color)
            else:
                # Inactive: dim
                for rel in (top, bottom):
                    idx = self._jewel_start + rel
                    if idx < self._driver.num_leds:
                        dim = tuple(int(c * 0.1) for c in chase_color)
                        self._driver.set(idx, *dim)

        # Stick: subtle ambient glow
        for i in range(self._stick_count):
            idx = self._stick_start + i
            if idx >= self._driver.num_leds:
                break
            # Gentle wave along stick
            wave = 0.05 + 0.05 * math.sin((self._wake_chase_phase + i * 0.5) * math.pi / 3)
            self._driver.set(idx, 
                           int(chase_color[0] * wave),
                           int(chase_color[1] * wave),
                           int(chase_color[2] * wave))
        
        self._driver.show()
