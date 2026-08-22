from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("speak.lang_detect")

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_EN_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "and", "but", "if", "or", "because",
    "what", "which", "who", "whom", "this", "that", "these", "those", "am",
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her",
    "its", "our", "their", "me", "him", "us", "them", "yes", "no", "ok", "please",
    "hello", "hi", "thanks", "thank", "sorry", "about", "tell", "know", "think",
})

try:
    from langdetect import detect as _detect_lang  # type: ignore
    from langdetect import DetectorFactory  # type: ignore

    DetectorFactory.seed = 0
except Exception:
    _detect_lang = None  # type: ignore


def network_available(timeout_s: float = 0.8) -> bool:
    """Best-effort online check for richer language detection."""
    try:
        import socket

        socket.create_connection(("1.1.1.1", 53), timeout=timeout_s).close()
        return True
    except Exception:
        return False


def normalize_lang(lang: Optional[str], fallback: str = "tr") -> str:
    raw = str(lang or "").strip().lower().replace("_", "-")
    if not raw or raw == "auto":
        return fallback
    if "-" in raw:
        raw = raw.split("-", 1)[0]
    return raw


def detect_text_language(text: str, *, default: str = "tr", prefer_online: bool = True) -> str:
    """Heuristic (+ optional langdetect when online) language tag for TTS/STT routing."""
    value = str(text or "").strip()
    if not value:
        return normalize_lang(default)

    if prefer_online and network_available() and _detect_lang is not None:
        try:
            detected = normalize_lang(str(_detect_lang(value)), fallback=default)
            if detected:
                return detected
        except Exception as exc:
            logger.debug("langdetect failed: %s", exc)

    tr_chars = sum(1 for ch in value if ch in _TR_CHARS)
    words = re.findall(r"[a-zA-Z']+", value.lower())
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)

    if tr_chars >= 2:
        return "tr"
    if tr_chars >= 1 and en_hits < 2:
        return "tr"
    if en_hits >= 2:
        return "en"
    if len(words) >= 4 and tr_chars == 0:
        return "en"
    if tr_chars == 0 and len(words) >= 2 and all(ord(c) < 128 for c in value if c.isalpha()):
        return "en"
    return normalize_lang(default)


def resolve_speak_language(
    text: str,
    *,
    explicit: Optional[str] = None,
    default: str = "tr",
    prefer_text: bool = True,
) -> str:
    """Pick language for Piper voice: spoken text wins over STT hint by default."""
    explicit_norm = normalize_lang(explicit, fallback=default)
    if not explicit or not str(explicit).strip():
        return detect_text_language(text, default=default)
    if not prefer_text:
        return explicit_norm
    detected = detect_text_language(text, default=default)
    if explicit_norm == detected:
        return detected
    return detected


def has_piper_voice_for_language(lang: str, piper_cfg: Dict[str, Any]) -> bool:
    """True when a Piper voice is explicitly mapped/available for the language."""
    lang = normalize_lang(lang, fallback="")
    if not lang:
        return False
    lang_map = piper_cfg.get("language_voices", {})
    if isinstance(lang_map, dict):
        for key in lang_map:
            key_norm = normalize_lang(str(key), fallback="")
            if key_norm and (lang == key_norm or lang.startswith(key_norm)):
                return True
    voices = piper_cfg.get("voices", {})
    return isinstance(voices, dict) and lang in voices


def piper_voice_for_language(lang: str, piper_cfg: Dict[str, Any]) -> str:
    """Map ISO-ish language code to piper.voices key."""
    lang = normalize_lang(lang, fallback=str(piper_cfg.get("voice", "tr") or "tr"))
    lang_map = piper_cfg.get("language_voices", {})
    voices = piper_cfg.get("voices", {}) if isinstance(piper_cfg.get("voices"), dict) else {}

    if isinstance(lang_map, dict):
        if lang in lang_map:
            return str(lang_map[lang]).strip().lower()
        for key, voice in lang_map.items():
            key_norm = normalize_lang(str(key), fallback="")
            if key_norm and (lang == key_norm or lang.startswith(key_norm)):
                return str(voice).strip().lower()

    if lang in voices:
        return lang
    if lang == "en" and "glados" in voices:
        return "glados"
    if lang.startswith("tr") and "tr" in voices:
        return "tr"
    return str(piper_cfg.get("voice", "tr")).strip().lower() or "tr"
