"""Adapter clients for ExpressionArbiter — re-exports for easy importing."""

from .neopixel_adapter import NeopixelAdapter
from .oled_adapter import OledAdapter
from .speak_adapter import SpeakAdapter
from .head_adapter import HeadAdapter, PiServoAdapter

__all__ = [
    "NeopixelAdapter",
    "OledAdapter",
    "SpeakAdapter",
    "HeadAdapter",
    "PiServoAdapter",
]