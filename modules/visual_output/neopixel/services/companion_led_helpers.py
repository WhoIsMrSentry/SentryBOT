from __future__ import annotations

import logging
from typing import Any, List, Tuple

logger = logging.getLogger("neopixel.companion_helpers")

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
    __slots__ = ("start", "count", "channel", "name", "reverse")

    def __init__(self, start: int, count: int, channel: int = 0, name: str = "brow", reverse: bool = False) -> None:
        self.start = start
        self.count = count
        self.channel = channel
        self.name = str(name or "brow")
        self.reverse = bool(reverse)
