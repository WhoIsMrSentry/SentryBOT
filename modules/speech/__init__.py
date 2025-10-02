"""Speech module package.

Provides audio capture from I2S/ALSA devices and offline speech recognition.
Follows DryCode principles and can be used as library or run as a service.
"""

from . import xSpeechService as xSpeechService  # re-export module for convenience

__all__ = [
    "config_loader",
    "xSpeechService",
]
