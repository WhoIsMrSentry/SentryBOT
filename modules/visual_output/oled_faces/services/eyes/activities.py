"""ACTIVITIES -- a looping "what I'm doing" status: a gaze pose + an overlay icon.
Each busy activity also wears a fitting face (see ACT_MOOD)."""
from __future__ import annotations

import math

from .primitives import rand
from .activity_drawings import (
    OVERLAYS,
    _PP_HMULT,
    _PP_CYCLE,
    _PP_SEG,
    _GLITCH_BEAT,
    _GLITCH_BEATS,
    _think,
    _headphones,
    _magnifier,
    _hammer,
    _typing,
    _arc_ring,
    _link_dots,
    _debug_bug,
    _building,
    _testing,
    _deploying,
    _ping_pong,
    _waiting,
    _glitch,
)

ACTIVITIES = (
    "idle", "thinking", "scanning", "searching", "processing", "working", "editing",
    "debugging", "building", "testing", "deploying", "connecting", "ping_pong",
    "listening", "waiting", "glitch",
)
ACT_MOOD = {
    "thinking": "focused", "scanning": "neutral", "searching": "focused",
    "working": "focused", "listening": "neutral", "editing": "smoking",
    "processing": "focused", "connecting": "attentive",
    "debugging": "suspicious", "building": "focused", "testing": "focused",
    "deploying": "neutral", "ping_pong": "attentive", "waiting": "bored", "glitch": "scared",
}

# Self-ending activities: glitch rolls out after ~3s windows (50% chance per window).
_GLITCH_ROLL_S = 3.0
_GLITCH_HEAL_ODD = 0.5


def _glitch_expired(now: float, start: float) -> bool:
    k = int((now - start) / _GLITCH_ROLL_S)
    return k >= 1 and rand(start + k * 7.31) < _GLITCH_HEAL_ODD


ACT_EXPIRY = {"glitch": _glitch_expired}


def pose(act, now):
    """Eased gaze target (x, y) + height multiplier for a looping activity."""
    if act == "thinking":
        return math.sin(now * 0.7) * 7, -9 + math.sin(now * 0.4) * 2, 1.0
    if act == "scanning":
        line = now * 1.0
        return (int(line % 1.0 * 4) / 3 * 2 - 1) * 13, (int(line) % 3 - 1) * 5, 1.0
    if act == "searching":
        return math.sin(now * 2.2) * 11 + math.sin(now * 1.3) * 5, math.sin(now * 1.7) * 5, 1.0
    if act == "working":
        return math.sin(now * 1.6) * 5, 4 + math.sin(now * 0.8) * 1, 0.85
    if act == "listening":
        return math.sin(now * 1.8) * 2, math.sin(now * 3.6) * 2, 1.0
    if act == "processing":
        return math.sin(now * 1.4) * 4, -2 + math.sin(now * 0.7), 0.92
    if act == "connecting":
        return math.sin(now * 1.5) * 3, math.sin(now * 2.0) * 2, 1.0
    if act == "debugging":
        return math.sin(now * 1.4) * 12 + math.sin(now * 3.1) * 3, 5 + math.sin(now * 4.0), 0.9
    if act == "building":
        return math.sin(now * 1.5) * 1.5, 4 + math.sin(now * 2.0) * 1.5, 0.92
    if act == "testing":
        return 5 + math.sin(now * 1.6) * 1.5, 5 + math.sin(now * 1.1) * 1.5, 0.95
    if act == "deploying":
        return math.sin(now * 0.25) * 4, 7 + math.sin(now * 1.7) * 1.2, 1.0
    if act == "ping_pong":
        return ((-6.0, -4.0, _PP_HMULT) if (now % _PP_CYCLE) < _PP_SEG
                else (6.0, 4.0, _PP_HMULT))
    if act == "waiting":
        return math.sin(now * 0.4) * 2, 2 + math.sin(now * 0.6), 1.0
    if act == "glitch":
        f = int(now / _GLITCH_BEAT) % len(_GLITCH_BEATS)
        if _GLITCH_BEATS[f] is None:
            return 0.0, 0.0, 1.0
        jx, jy = rand(f), rand(f, 7)
        return (round(jx * 4) - 2) * 3, (round(jy * 2) - 1) * 2, 1.0
    return 0.0, 0.0, 1.0


__all__ = [
    "ACTIVITIES",
    "ACT_MOOD",
    "ACT_EXPIRY",
    "OVERLAYS",
    "pose",
]
