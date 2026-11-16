"""Canonical color parsing and normalization utilities for SentryBOT."""
from __future__ import annotations

from typing import Any, Optional, Tuple

_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 128, 0),
    "purple": (128, 0, 128),
    "magenta": (255, 0, 255),
    "cyan": (0, 255, 255),
    "white": (255, 255, 255),
    "off": (0, 0, 0),
    "black": (0, 0, 0),
}


def clamp_rgb(r: Any, g: Any, b: Any) -> Tuple[int, int, int]:
    """Clamp r, g, b values cleanly into [0, 255]."""
    return (
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Linearly interpolate between two RGB colors with t clamped to [0.0, 1.0]."""
    u = max(0.0, min(1.0, float(t)))
    return clamp_rgb(
        round(c1[0] + (c2[0] - c1[0]) * u),
        round(c1[1] + (c2[1] - c1[1]) * u),
        round(c1[2] + (c2[2] - c1[2]) * u),
    )


def normalize_color(color: Any) -> Optional[Tuple[int, int, int]]:
    """Normalize a color specification (list, tuple, hex, CSV, or named color) into clamped (r, g, b)."""
    if color is None:
        return None
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        try:
            return clamp_rgb(color[0], color[1], color[2])
        except (TypeError, ValueError):
            return None
    if isinstance(color, str):
        s = color.strip()
        if s.lower() in _NAMED_COLORS:
            return _NAMED_COLORS[s.lower()]
        if s.startswith("#") and len(s) in (7, 9):
            try:
                v = int(s[1:7], 16)
                return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
            except ValueError:
                return None
        parts = s.split(",")
        if len(parts) == 3:
            try:
                return clamp_rgb(parts[0].strip(), parts[1].strip(), parts[2].strip())
            except (TypeError, ValueError):
                return None
    return None


def parse_color(raw: Any) -> Optional[Tuple[int, int, int]]:
    """Alias for normalize_color."""
    return normalize_color(raw)


__all__ = ["clamp_rgb", "lerp_color", "normalize_color", "parse_color"]

