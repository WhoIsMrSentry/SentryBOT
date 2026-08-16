"""Online STT (Speech-to-Text) module using Google Speech Recognition (free, no LLM quota)."""

from __future__ import annotations

import logging
from typing import Optional

try:
    import speech_recognition as sr
except ImportError:
    sr = None  # type: ignore

logger = logging.getLogger("speech.online_stt")

_recognizer = sr.Recognizer() if sr is not None else None


def transcribe_google(
    pcm_bytes: bytes,
    samplerate: int = 16000,
    language: str = "tr-TR",
    timeout_s: float = 3.0,
) -> Optional[str]:
    """Transcribe audio PCM bytes using free Google Speech Recognition."""
    if _recognizer is None or not pcm_bytes or len(pcm_bytes) < 3200:
        return None

    try:
        audio_data = sr.AudioData(pcm_bytes, sample_rate=samplerate, sample_width=2)
        # Recognize using Google Speech Recognition (tr-TR)
        text = _recognizer.recognize_google(audio_data, language=language)
        result = str(text or "").strip()
        if result:
            logger.info("Google STT transcribed (%s): %r", language, result)
            return result
    except getattr(sr, "UnknownValueError", Exception):
        # Audio was unintelligible or silence
        logger.debug("Google STT could not understand audio")
    except getattr(sr, "RequestError", Exception) as e:
        logger.warning("Google STT service error: %s", e)
    except Exception as exc:
        logger.debug("Google STT unexpected error: %s", exc)

    return None
