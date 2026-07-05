"""Companion LED modes: VU-meter strip, jewel thinking ring, center eye.

Layout (config-driven, default): indices 0-6 = NeoPixel Jewel (0 = center eye),
indices 7+ = straight strip for audio level display.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, Optional, Tuple

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

        thinking = self._cfg.get("thinking", {}) if isinstance(self._cfg.get("thinking"), dict) else {}
        self._think_step_ms = float(thinking.get("step_ms", 120))
        eye = self._cfg.get("eye", {}) if isinstance(self._cfg.get("eye"), dict) else {}
        self._eye_breathe_ms = float(eye.get("breathe_ms", 800))
        vu = self._cfg.get("vu", {}) if isinstance(self._cfg.get("vu"), dict) else {}
        self._vu_smoothing = float(vu.get("smoothing", 0.35))
        self._vu_min = float(vu.get("min_level", 0.04))
        self._tick_ms = float(self._cfg.get("tick_ms", 50))

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mode = "off"
        self._vu_level = 0.0
        self._vu_target = 0.0
        self._think_phase = 0
        self._eye_phase = 0.0

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
            except Exception as exc:
                logger.debug("companion frame failed: %s", exc)
            time.sleep(interval)

    def _clear_companion_range(self) -> None:
        end = self._stick_start + self._stick_count
        for i in range(self._jewel_start, min(end, self._driver.num_leds)):
            self._driver.set(i, 0, 0, 0)
        self._driver.show()

    def _render_vu_frame(self) -> None:
        with self._lock:
            self._vu_level += (self._vu_target - self._vu_level) * self._vu_smoothing
            level = self._vu_level
            eye = self._eye_color

        # Stick VU meter
        lit = int(round(level * self._stick_count))
        lit = max(0, min(self._stick_count, lit))
        for i in range(self._stick_count):
            idx = self._stick_start + i
            if idx >= self._driver.num_leds:
                break
            if i < lit:
                self._driver.set(idx, *self._vu_bar)
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
