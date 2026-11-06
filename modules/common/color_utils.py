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


def normalize_color(color: Any) -> Optional[Tuple[int, int, int]]:
    """Normalize a color specification (list, tuple, hex string, named color) into (r, g, b) 0-255."""
    if color is None:
        return None
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        try:
            return (
                max(0, min(255, int(color[0]))),
                max(0, min(255, int(color[1]))),
                max(0, min(255, int(color[2]))),
            )
        except (TypeError, ValueError):
            return None
    if isinstance(color, str):
        s = color.strip()
        if s.lower() in _NAMED_COLORS:
            return _NAMED_COLORS[s.lower()]
        if s.startswith("#") and len(s) >= 7:
            try:
                v = int(s[1:7], 16)
                return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
            except ValueError:
                return None
    return None


def parse_color(raw: Any) -> Optional[Tuple[int, int, int]]:
    """Alias for normalize_color."""
    return normalize_color(raw)


__all__ = ["normalize_color", "parse_color"]

