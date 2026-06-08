"""Procedural 1-bit face rasteriser.

Fallback used when a pre-baked OLED bitmap asset is missing from disk. Draws a
simple, recognisable face (eyes + brows + mouth) for a given emotion so the
robot's eyes stay expressive even on a fresh checkout without committed binary
bitmaps.

The renderer is hardware-agnostic: it draws through a ``plot(x, y)`` callback so
it can target the SSD1306 page buffer on a Pi or a plain grid in tests.
"""

from __future__ import annotations

from typing import Callable, Dict

try:
    from modules.common.emotion_vocab import get_vocab as _get_emotion_vocab
except Exception:  # pragma: no cover - optional dependency
    _get_emotion_vocab = None

Plot = Callable[[int, int], None]


# Per-style eye/mouth/brow descriptors. Keyed by canonical emotion plus a few
# direct gaze/blink poses that are not emotions.
_EYE_OPEN = "open"
_EYE_HAPPY = "happy"      # upward arc ^ ^
_EYE_NARROW = "narrow"    # half-closed line
_EYE_WIDE = "wide"        # big round
_EYE_CLOSED = "closed"    # flat line (blink)

_MOUTH_SMILE = "smile"
_MOUTH_FROWN = "frown"
_MOUTH_FLAT = "flat"
_MOUTH_OPEN = "open"      # small "o"

_STYLES: Dict[str, Dict[str, object]] = {
    "neutral":    {"eye": _EYE_OPEN,   "mouth": _MOUTH_FLAT,  "brow": 0},
    "joy":        {"eye": _EYE_HAPPY,  "mouth": _MOUTH_SMILE, "brow": 0},
    "excitement": {"eye": _EYE_WIDE,   "mouth": _MOUTH_SMILE, "brow": 0},
    "love":       {"eye": _EYE_HAPPY,  "mouth": _MOUTH_SMILE, "brow": 0},
    "sadness":    {"eye": _EYE_NARROW, "mouth": _MOUTH_FROWN, "brow": 1},
    "tired":      {"eye": _EYE_NARROW, "mouth": _MOUTH_FLAT,  "brow": 0},
    "bored":      {"eye": _EYE_NARROW, "mouth": _MOUTH_FLAT,  "brow": 0},
    "fear":       {"eye": _EYE_WIDE,   "mouth": _MOUTH_OPEN,  "brow": 1},
    "worried":    {"eye": _EYE_OPEN,   "mouth": _MOUTH_FROWN, "brow": 1},
    "anger":      {"eye": _EYE_OPEN,   "mouth": _MOUTH_FROWN, "brow": -1},
    "furious":    {"eye": _EYE_NARROW, "mouth": _MOUTH_FROWN, "brow": -1},
    "surprise":   {"eye": _EYE_WIDE,   "mouth": _MOUTH_OPEN,  "brow": 0},
    "curiosity":  {"eye": _EYE_OPEN,   "mouth": _MOUTH_FLAT,  "brow": 0},
    "disgust":    {"eye": _EYE_NARROW, "mouth": _MOUTH_FROWN, "brow": -1},
    "confusion":  {"eye": _EYE_OPEN,   "mouth": _MOUTH_FLAT,  "brow": 1},
}

# Direct (non-emotion) poses handled before vocab resolution.
_DIRECT: Dict[str, Dict[str, object]] = {
    "normal":  {"eye": _EYE_OPEN,   "mouth": _MOUTH_FLAT,  "brow": 0},
    "blink":   {"eye": _EYE_CLOSED, "mouth": _MOUTH_FLAT,  "brow": 0},
    "happy":   {"eye": _EYE_HAPPY,  "mouth": _MOUTH_SMILE, "brow": 0},
    "sad":     {"eye": _EYE_NARROW, "mouth": _MOUTH_FROWN, "brow": 1},
    "angry":   {"eye": _EYE_OPEN,   "mouth": _MOUTH_FROWN, "brow": -1},
    "furious": {"eye": _EYE_NARROW, "mouth": _MOUTH_FROWN, "brow": -1},
    "sleepy":  {"eye": _EYE_NARROW, "mouth": _MOUTH_FLAT,  "brow": 0},
    "surprised": {"eye": _EYE_WIDE, "mouth": _MOUTH_OPEN,  "brow": 0},
    "focused": {"eye": _EYE_NARROW, "mouth": _MOUTH_FLAT,  "brow": 0},
}


def _style_for(name: str) -> Dict[str, object]:
    key = str(name or "").strip().lower()
    if key in _DIRECT:
        return _DIRECT[key]
    canon = key
    if _get_emotion_vocab is not None:
        try:
            canon = _get_emotion_vocab().canonical(key)
        except Exception:
            canon = key
    return _STYLES.get(canon, _STYLES["neutral"])


def _hline(plot: Plot, x0: int, x1: int, y: int) -> None:
    if x1 < x0:
        x0, x1 = x1, x0
    for x in range(x0, x1 + 1):
        plot(x, y)


def _vline(plot: Plot, x: int, y0: int, y1: int) -> None:
    if y1 < y0:
        y0, y1 = y1, y0
    for y in range(y0, y1 + 1):
        plot(x, y)


def _rect(plot: Plot, x0: int, y0: int, x1: int, y1: int, fill: bool) -> None:
    if fill:
        for y in range(y0, y1 + 1):
            _hline(plot, x0, x1, y)
    else:
        _hline(plot, x0, x1, y0)
        _hline(plot, x0, x1, y1)
        _vline(plot, x0, y0, y1)
        _vline(plot, x1, y0, y1)


def _arc_up(plot: Plot, cx: int, y: int, half: int) -> None:
    # simple upward chevron ^ for happy eyes / smile
    for dx in range(-half, half + 1):
        plot(cx + dx, y + abs(dx) // 2)


def _arc_down(plot: Plot, cx: int, y: int, half: int) -> None:
    for dx in range(-half, half + 1):
        plot(cx + dx, y - abs(dx) // 2)


def _draw_eye(plot: Plot, cx: int, cy: int, shape: str) -> None:
    if shape == _EYE_CLOSED:
        _hline(plot, cx - 7, cx + 7, cy)
    elif shape == _EYE_NARROW:
        _rect(plot, cx - 7, cy - 1, cx + 7, cy + 2, fill=True)
    elif shape == _EYE_WIDE:
        _rect(plot, cx - 8, cy - 8, cx + 8, cy + 8, fill=False)
        _rect(plot, cx - 6, cy - 6, cx + 6, cy + 6, fill=True)
    elif shape == _EYE_HAPPY:
        _arc_up(plot, cx, cy - 2, 7)
        _arc_up(plot, cx, cy - 1, 7)
    else:  # open
        _rect(plot, cx - 6, cy - 6, cx + 6, cy + 6, fill=True)


def _draw_brow(plot: Plot, cx: int, cy: int, direction: int) -> None:
    if direction == 0:
        return
    if direction < 0:  # angry: inner-down
        _arc_down(plot, cx, cy, 7)
    else:  # worried/sad: inner-up
        _arc_up(plot, cx, cy, 7)


def _draw_mouth(plot: Plot, cx: int, cy: int, shape: str) -> None:
    if shape == _MOUTH_SMILE:
        _arc_up(plot, cx, cy - 3, 10)
    elif shape == _MOUTH_FROWN:
        _arc_down(plot, cx, cy + 3, 10)
    elif shape == _MOUTH_OPEN:
        _rect(plot, cx - 4, cy - 4, cx + 4, cy + 4, fill=False)
    else:  # flat
        _hline(plot, cx - 8, cx + 8, cy)


def draw_face(name: str, width: int, height: int, plot: Plot) -> str:
    """Rasterise a face for ``name`` via ``plot``; returns the resolved style id."""
    style = _style_for(name)
    cx = width // 2
    eye_y = height // 3
    eye_dx = width // 4
    left_x = cx - eye_dx
    right_x = cx + eye_dx
    mouth_y = (height * 3) // 4

    brow = int(style.get("brow", 0))
    eye_shape = str(style.get("eye", _EYE_OPEN))
    mouth_shape = str(style.get("mouth", _MOUTH_FLAT))

    if brow != 0:
        _draw_brow(plot, left_x, eye_y - 10, brow)
        _draw_brow(plot, right_x, eye_y - 10, brow)
    _draw_eye(plot, left_x, eye_y, eye_shape)
    _draw_eye(plot, right_x, eye_y, eye_shape)
    _draw_mouth(plot, cx, mouth_y, mouth_shape)
    return f"{eye_shape}/{mouth_shape}/{brow}"


__all__ = ["draw_face"]
