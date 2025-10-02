from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class EarPose:
    left: float
    right: float


EMOTION_POSES: Dict[str, EarPose] = {
    # 90: up, <90 down-forward, >90 back
    "neutral": EarPose(90, 90),
    "joy": EarPose(70, 70),
    "fear": EarPose(110, 110),
    "anger": EarPose(80, 100),
    "sadness": EarPose(100, 100),
    "surprise": EarPose(60, 60),
    "curiosity": EarPose(75, 85),
}


def gesture_wakeword() -> Tuple[float, float]:
    # quick raise both then relax
    return (60, 60)


def gesture_sound() -> Tuple[float, float]:
    # tilt to one side inquisitively
    return (80, 100)
