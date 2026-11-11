from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from modules.common.color_utils import lerp_color as _common_lerp_color, normalize_color

logger = logging.getLogger("neopixel.companion_helpers")

Color = Tuple[int, int, int]


def _parse_hex_color(raw: Any, default: Color) -> Color:
    parsed = normalize_color(raw)
    return parsed if parsed is not None else default


def _lerp_color(c1: Color, c2: Color, t: float) -> Color:
    return _common_lerp_color(c1, c2, t)


def _safe_float(
    value: Any,
    default: float,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    if minimum is not None:
        v = max(minimum, v)
    if maximum is not None:
        v = min(maximum, v)
    return v


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
