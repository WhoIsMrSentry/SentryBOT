"""Map legacy Irisoled / SentryBOT face names to Pip eye-engine actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .eyes.activities import ACTIVITIES
from .eyes.gestures import BLINKS, GESTURES_FN
from .eyes.moods import MOODS

# Legacy bitmap labels still emitted by emotion_vocab / config.
_MOOD_ALIASES: Dict[str, str] = {
    "normal": "neutral",
    "excited": "happy",
    "look_down": "neutral",
    "look_left": "neutral",
    "look_right": "neutral",
    "look_up": "neutral",
    "blink_up": "neutral",
    "blink_down": "neutral",
    "wink_left": "neutral",
    "wink_right": "neutral",
    "battery": "standby",
    "battery_full": "happy",
    "battery_low": "worried",
    "left_signal": "neutral",
    "right_signal": "neutral",
    "logo": "attentive",
    "mode": "standby",
    "warning": "alert",
}

# Legacy JSON animation names -> (kind, target) where kind is mood|gesture|activity.
_LEGACY_ANIMATIONS: Dict[str, Tuple[str, str]] = {
    "scan": ("activity", "scanning"),
    "emotive": ("activity", "listening"),
    "sleep": ("mood", "sleepy"),
    "alert": ("mood", "alert"),
    "wink": ("gesture", "wink"),
    "blink": ("gesture", "blink"),
    "icons": ("activity", "processing"),
    "all": ("gesture", "excited"),
}

# Gaze poses that were static bitmaps; play as one-shot gestures.
_GAZE_GESTURES: Dict[str, str] = {
    "look_left": "look_left",
    "look_right": "look_right",
    "look_up": "look_up",
    "look_down": "look_down",
    "blink_up": "blink_up",
    "blink_down": "blink_down",
    "wink_left": "wink_left",
    "wink_right": "wink_right",
    "left_signal": "look_left",
    "right_signal": "look_right",
}


@dataclass(frozen=True)
class FaceCommand:
    mood: Optional[str] = None
    gesture: Optional[str] = None
    activity: Optional[str] = None


def catalog_moods() -> Tuple[str, ...]:
    return tuple(sorted(set(MOODS) | set(_MOOD_ALIASES)))


def catalog_animations() -> Tuple[str, ...]:
    legacy = tuple(_LEGACY_ANIMATIONS)
    gestures = tuple(BLINKS) + tuple(GESTURES_FN)
    activities = tuple(a for a in ACTIVITIES if a != "idle")
    return tuple(sorted(set(legacy) | set(gestures) | set(activities)))


def resolve_mood(name: str) -> str:
    key = str(name or "neutral").strip().lower()
    if key in MOODS:
        return key
    return _MOOD_ALIASES.get(key, "neutral")


def resolve_bitmap(name: str) -> FaceCommand:
    key = str(name or "neutral").strip().lower()
    mood = resolve_mood(key)
    gesture = _GAZE_GESTURES.get(key)
    return FaceCommand(mood=mood, gesture=gesture)


def resolve_gesture(name: str) -> FaceCommand:
    key = str(name or "").strip().lower()
    if key in BLINKS or key in GESTURES_FN:
        return FaceCommand(gesture=key)
    return FaceCommand(mood="neutral")


def resolve_animation(name: str) -> FaceCommand:
    key = str(name or "").strip().lower()
    if key in _LEGACY_ANIMATIONS:
        kind, target = _LEGACY_ANIMATIONS[key]
        if kind == "mood":
            return FaceCommand(mood=target, activity="idle")
        if kind == "gesture":
            return FaceCommand(gesture=target)
        if kind == "activity":
            return FaceCommand(activity=target)
    if key in BLINKS or key in GESTURES_FN:
        return FaceCommand(gesture=key)
    if key in ACTIVITIES:
        return FaceCommand(activity=key if key != "idle" else "idle")
    return FaceCommand(mood="alert")


def resolve_logo() -> FaceCommand:
    return FaceCommand(mood="attentive", gesture="boot_up")
