from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from modules.speech.services.recognizer import Recognizer

logger = logging.getLogger("speech.stt_language")

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_EN_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "what", "which", "who", "how", "all", "some", "not", "and", "but", "if", "or",
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "me",
    "please", "hello", "hi", "thanks", "thank", "sorry", "about", "tell",
    "introduce", "yourself", "help", "yes", "no",
})


def _detect_language(text: str, *, default: str) -> str:
    from modules.speak.services.lang_detect import detect_text_language

    return detect_text_language(text, default=default)


def _transcript_score(text: str, target_lang: str) -> float:
    """Score how well a transcript matches the target language."""
    value = str(text or "").strip()
    if not value:
        return 0.0
    words = re.findall(r"[a-zA-Z']+", value.lower())
    if not words:
        return 0.0

    tr_chars = sum(1 for ch in value if ch in _TR_CHARS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    detected = _detect_language(value, default="tr")

    if target_lang == "en":
        score = en_hits * 0.45
        if detected == "en":
            score += 3.0
        if tr_chars == 0:
            score += 1.2
        if tr_chars >= 2 and en_hits < 2:
            score -= 2.5
        if len(words) >= 3 and tr_chars == 0:
            score += 0.8
        return score

    score = 1.0 if detected == "tr" else 0.4
    score += tr_chars * 0.35
    score += min(en_hits, 2) * 0.1
    if detected == "en" and tr_chars == 0 and en_hits >= 3:
        score -= 1.5
    return score


def resolve_stt_text_and_language(
    text: str,
    pcm: bytes,
    *,
    primary: Recognizer,
    secondary: Optional[Recognizer],
    primary_lang: str = "tr",
    secondary_lang: str = "en",
    default_language: str = "tr",
    auto_switch_model: bool = True,
    dual_decode_margin: float = 0.6,
) -> Tuple[str, str]:
    """Pick TR or EN transcript by dual-decoding utterance audio when possible."""
    primary_text = str(text or "").strip()
    if not primary_text and not pcm:
        return "", default_language

    if not auto_switch_model or secondary is None:
        lang = _detect_language(primary_text, default=default_language) if primary_text else default_language
        return primary_text, lang

    secondary_text = ""
    if pcm:
        try:
            secondary_text = str(secondary.recognize_pcm(pcm) or "").strip()
        except FileNotFoundError:
            logger.warning(f"{secondary_lang.upper()} Vosk model missing; keeping primary transcript only")
        except Exception as exc:
            logger.debug("secondary STT failed: %s", exc)

    if not secondary_text:
        lang = _detect_language(primary_text, default=default_language) if primary_text else default_language
        return primary_text, lang

    if not primary_text:
        lang = _detect_language(secondary_text, default=default_language)
        logger.info("STT language=%s (primary empty, secondary only)", lang)
        return secondary_text, lang

    # Map the outputs to the expected tr/en variables based on the language configuration
    if primary_lang.startswith("tr"):
        tr_text = primary_text
        en_text = secondary_text
    else:
        tr_text = secondary_text
        en_text = primary_text

    tr_score = _transcript_score(tr_text, "tr")
    en_score = _transcript_score(en_text, "en")
    en_words = re.findall(r"[a-zA-Z']+", en_text.lower())
    en_stop_hits = sum(1 for w in en_words if w in _EN_STOPWORDS)
    tr_chars_in_tr = sum(1 for ch in tr_text if ch in _TR_CHARS)

    pick_en = en_score > tr_score + dual_decode_margin
    # Favor English if the English model produces stop words, to prevent TR hallucination
    if not pick_en and en_stop_hits >= 2 and en_score >= tr_score - 0.15:
        if tr_chars_in_tr == 0 or en_score >= tr_score:
            pick_en = True
    if not pick_en and en_stop_hits >= 1 and tr_chars_in_tr >= 2 and en_score > tr_score:
        pick_en = True

    if pick_en:
        lang = _detect_language(en_text, default=default_language)
        logger.info(
            "STT picked vosk-en (tr_score=%.2f en_score=%.2f tr=%r en=%r)",
            tr_score,
            en_score,
            tr_text[:48],
            en_text[:48],
        )
        return en_text, "en" if lang != "tr" else lang

    lang = _detect_language(tr_text, default=default_language)
    if tr_score >= en_score:
        logger.info(
            "STT picked vosk-tr (tr_score=%.2f en_score=%.2f tr=%r en=%r)",
            tr_score,
            en_score,
            tr_text[:48],
            en_text[:48],
        )
        return tr_text, lang
    
    lang = _detect_language(en_text, default=default_language)
    logger.info(
        "STT picked vosk-en (fallback) (tr_score=%.2f en_score=%.2f tr=%r en=%r)",
        tr_score,
        en_score,
        tr_text[:48],
        en_text[:48],
    )
    return en_text, "en" if lang != "tr" else lang
