"""Speech module package.

Provides audio capture from I2S/ALSA devices and offline speech recognition.
Follows DryCode principles and can be used as library or run as a service.
"""

from . import config_loader

__all__ = [
    "config_loader",
    "xSpeechService",
]


def __getattr__(name: str):
    if name == "xSpeechService":
        from .xSpeechService import SpeechService as xSpeechService  # noqa: N811

        return xSpeechService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
