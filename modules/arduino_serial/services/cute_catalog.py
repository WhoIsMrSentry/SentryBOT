from __future__ import annotations

from typing import Any, Dict

CUTE_SOUND_CATALOG: Dict[str, Dict[str, Any]] = {
    "connection": {"animation": "PULSE", "color": "0,180,80", "iterations": 1},
    "disconnection": {
        "animation": "THEATER_CHASE",
        "color": "220,30,30",
        "iterations": 1,
    },
    "button_pushed": {
        "animation": "PULSE",
        "color": "180,180,180",
        "iterations": 1,
    },
    "mode1": {"animation": "WAVE", "color": "0,180,255", "iterations": 1},
    "mode2": {"animation": "WAVE", "color": "180,0,255", "iterations": 1},
    "mode3": {"animation": "WAVE", "color": "255,80,0", "iterations": 1},
    "happy": {"animation": "WAVE", "color": "255,220,0", "iterations": 2},
    "happy_short": {"animation": "PULSE", "color": "255,220,0", "iterations": 1},
    "super_happy": {"animation": "RAINBOW", "color": "", "iterations": 1},
    "sad": {"animation": "BREATHE", "color": "0,70,255", "iterations": 2},
    "surprise": {"animation": "TWINKLE", "color": "255,255,255", "iterations": 2},
    "ohooh": {
        "animation": "THEATER_CHASE",
        "color": "255,255,255",
        "iterations": 1,
    },
    "ohooh2": {
        "animation": "THEATER_CHASE",
        "color": "255,255,255",
        "iterations": 2,
    },
    "cuddly": {"animation": "BREATHE", "color": "255,50,150", "iterations": 2},
    "confused": {"animation": "PULSE", "color": "170,0,255", "iterations": 2},
    "sleeping": {"animation": "BREATHE", "color": "20,40,120", "iterations": 2},
    "fart1": {"animation": "ALTERNATING", "color": "20,180,20", "iterations": 2},
    "fart2": {"animation": "ALTERNATING", "color": "40,220,40", "iterations": 2},
    "fart3": {"animation": "ALTERNATING", "color": "10,120,10", "iterations": 2},
    "jump": {"animation": "COMET", "color": "255,255,255", "iterations": 2},
}

EMOTION_TO_CUTE: Dict[str, str] = {
    "happy": "happy",
    "super_happy": "super_happy",
    "sad": "sad",
    "surprise": "surprise",
    "confused": "confused",
    "sleeping": "sleeping",
    "connected": "connection",
    "disconnected": "disconnection",
}
