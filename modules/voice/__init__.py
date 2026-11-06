"""Voice subsystem package (speech, wakeword, speaker_id, speak, audio_router)."""
from __future__ import annotations

from .audio_router import get_audio_router, AudioRouter

__all__ = ["get_audio_router", "AudioRouter"]
