"""Online STT (Speech-to-Text) module using Google Speech Recognition (free, multi-language, no LLM quota)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import speech_recognition as sr
except ImportError:
    sr = None  # type: ignore

logger = logging.getLogger("speech.online_stt")

_recognizer = sr.Recognizer() if sr is not None else None

# Map standard 2-letter codes to full BCP-47 language tags for Google STT
_LANG_TAG_MAP = {
    "tr": "tr-TR",
    "en": "en-US",
    "de": "de-DE",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "ru": "ru-RU",
    "ar": "ar-SA",
}


def _normalize_lang_tag(code: str) -> str:
    cleaned = str(code or "").strip()
    if not cleaned:
        return "tr-TR"
    if "-" in cleaned or "_" in cleaned:
        return cleaned.replace("_", "-")
    return _LANG_TAG_MAP.get(cleaned.lower(), f"{cleaned.lower()}-{cleaned.upper()}")


def transcribe_single_language(
    audio_data: Any,
    lang_tag: str,
) -> Tuple[str, str]:
    """Transcribe single audio data for a given language tag."""
    if _recognizer is None:
        return "", lang_tag
    try:
        text = _recognizer.recognize_google(audio_data, language=lang_tag)
        return str(text or "").strip(), lang_tag
    except getattr(sr, "UnknownValueError", Exception):
        return "", lang_tag
    except getattr(sr, "RequestError", Exception) as e:
        logger.warning("Google STT network error for %s: %s", lang_tag, e)
        return "", lang_tag
    except Exception as exc:
        logger.debug("Google STT error for %s: %s", lang_tag, exc)
        return "", lang_tag


def transcribe_google_multilang(
    pcm_bytes: bytes,
    samplerate: int = 16000,
    languages: Optional[List[str]] = None,
    default_lang: str = "tr",
) -> Tuple[str, str]:
    """Transcribe PCM audio across multiple candidate languages and pick the best transcript and detected language.

    Returns:
        tuple[str, str]: (best_text, detected_language_code e.g. 'tr' or 'en')
    """
    if _recognizer is None or not pcm_bytes or len(pcm_bytes) < 3200:
        return "", default_lang

    from modules.speech.services.stt_language import _detect_language, _transcript_score

    lang_list = languages or ["tr", "en"]
    if default_lang not in lang_list:
        lang_list = [default_lang] + [l for l in lang_list if l != default_lang]

    seen: set[str] = set()
    tags_to_query: List[str] = []
    for l in lang_list:
        tag = _normalize_lang_tag(l)
        if tag not in seen:
            seen.add(tag)
            tags_to_query.append(tag)

    audio_data = sr.AudioData(pcm_bytes, sample_rate=samplerate, sample_width=2)
    candidates: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=min(4, len(tags_to_query))) as executor:
        futures = {
            executor.submit(transcribe_single_language, audio_data, tag): tag
            for tag in tags_to_query
        }
        for fut in as_completed(futures):
            try:
                text, tag = fut.result()
                if text:
                    short_code = tag.split("-")[0].lower()
                    candidates[short_code] = text
            except Exception as e:
                logger.debug("Multi-lang STT worker failed: %s", e)

    if not candidates:
        return "", default_lang

    if len(candidates) == 1:
        lang_code, text = next(iter(candidates.items()))
        logger.info("Google STT single result: [%s] %r", lang_code, text)
        return text, lang_code

    best_lang = default_lang
    best_text = ""
    best_score = -999.0

    for lang, text in candidates.items():
        score = _transcript_score(text, lang)
        logger.info("Google STT candidate: [%s] %r (score=%.2f)", lang, text, score)
        if score > best_score:
            best_score = score
            best_lang = lang
            best_text = text

    if not best_text:
        first_lang, first_text = next(iter(candidates.items()))
        return first_text, first_lang

    detected_lang = _detect_language(best_text, default=best_lang)
    logger.info("Google STT winner: [%s] %r (detected=%s score=%.2f)", best_lang, best_text, detected_lang, best_score)
    return best_text, detected_lang
