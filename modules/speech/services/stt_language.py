from __future__ import annotations

import logging
from typing import Optional, Tuple

from modules.speech.services.recognizer import Recognizer

logger = logging.getLogger("speech.stt_language")


def _detect_language(text: str, *, default: str) -> str:
    from modules.speak.services.lang_detect import detect_text_language

    return detect_text_language(text, default=default)


def resolve_stt_text_and_language(
    text: str,
    pcm: bytes,
    *,
    primary: Recognizer,
    secondary: Optional[Recognizer],
    default_language: str = "tr",
    auto_switch_model: bool = True,
) -> Tuple[str, str]:
    """Detect language from transcript; optionally re-decode with EN Vosk."""
    cleaned = str(text or "").strip()
    lang = _detect_language(cleaned, default=default_language)
    if not cleaned:
        return cleaned, lang
    if not auto_switch_model or secondary is None or lang != "en":
        return cleaned, lang
    if not pcm:
        return cleaned, lang
    try:
        alt_text = secondary.recognize_pcm(pcm)
    except FileNotFoundError:
        logger.warning("English Vosk model missing; keeping primary transcript")
        return cleaned, lang
    except Exception as exc:
        logger.debug("secondary STT failed: %s", exc)
        return cleaned, lang
    alt_text = str(alt_text or "").strip()
    if not alt_text:
        return cleaned, lang
    alt_lang = _detect_language(alt_text, default=default_language)
    if alt_lang == "en":
        logger.info("STT language=en (re-decoded with vosk-en)")
        return alt_text, "en"
    return cleaned, lang
