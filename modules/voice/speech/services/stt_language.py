from __future__ import annotations

import logging
import re
from typing import Dict, Optional, Tuple

from modules.voice.speak.services.lang_detect import (
    _EN_STOPWORDS,
    _TR_CHARS,
    _TR_STOPWORDS,
    _WEAK_EN_TOKENS,
    count_turkish_morph_hits,
)
from modules.voice.speech.services.recognizer import Recognizer

logger = logging.getLogger("speech.stt_language")


def _detect_language(text: str, *, default: str, prefer_online: bool = True) -> str:
    from modules.voice.speak.services.lang_detect import detect_text_language

    return detect_text_language(text, default=default, prefer_online=prefer_online)


def _transcript_score(text: str, target_lang: str, *, default_lang: str = "tr") -> float:
    """Score how well a transcript matches the target language without biasing toward short EN noise."""
    value = str(text or "").strip()
    if not value:
        return 0.0
    words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ']+", value.lower())
    if not words:
        return 0.0

    tgt = str(target_lang or "tr").split("-", 1)[0].strip().lower()
    def_lang = str(default_lang or "tr").split("-", 1)[0].strip().lower()

    tr_chars = sum(1 for ch in value if ch in _TR_CHARS)
    tr_hits = sum(1 for w in words if w in _TR_STOPWORDS)
    tr_morph = count_turkish_morph_hits(words)
    tr_evidence = tr_hits + tr_morph
    strong_en_hits = sum(1 for w in words if w in _EN_STOPWORDS and w not in _WEAK_EN_TOKENS)
    weak_en_hits = sum(1 for w in words if w in _WEAK_EN_TOKENS)

    # Pass target language as fallback default so EN/TR neutral short phrases aren't misscored
    detected = _detect_language(value, default=tgt or "tr", prefer_online=True)
    default_prior = 1.2 if (def_lang and tgt == def_lang) else 0.0

    if tgt == "tr":
        score = 2.0 if detected == "tr" else 1.0
        score += tr_hits * 1.5
        score += tr_morph * 1.5
        score += tr_chars * 1.0
        if len(words) >= 2 and tr_evidence >= 1:
            score += 2.0
        if detected == "en" and tr_chars == 0 and tr_evidence == 0 and strong_en_hits >= 2:
            score -= 2.0
        score += default_prior
        return score

    if tgt == "en":
        if strong_en_hits == 0 and weak_en_hits > 0 and len(words) <= 3:
            # Weak single-letter / interjection shards like "a Microsoft" should not overpower valid primary TR
            return 1.2 + weak_en_hits * 0.3
        score = 2.0 if detected == "en" else 0.5
        score += strong_en_hits * 1.5
        score += weak_en_hits * 0.25
        if len(words) >= 2 and (strong_en_hits >= 2 or (strong_en_hits >= 1 and len(words) >= 3)):
            score += 2.0
        elif len(words) >= 2 and strong_en_hits >= 1 and default_prior == 0.0:
            score += 1.0
        if tr_chars >= 1 or tr_evidence >= 1:
            score -= 3.0
        score += default_prior
        return score

    # Generic languages: trust langdetect + transcript length
    score = 2.0 if detected == tgt else 0.5
    score += min(len(words), 8) * 0.2
    score += default_prior
    return score


def _decode_pcm(recognizer: Recognizer, pcm: bytes) -> str:
    try:
        raw = recognizer.recognize_pcm(pcm)
        if isinstance(raw, (tuple, list)):
            raw = raw[0] if raw else ""
        return str(raw or "").strip()
    except FileNotFoundError:
        lang = getattr(getattr(recognizer, "cfg", None), "language", "?")
        logger.warning("%s STT model missing; skipping dual-decode for that language", lang)
    except Exception as exc:
        logger.debug("secondary STT failed: %s", exc)
    return ""


def resolve_stt_text_and_language(
    text: str,
    pcm: bytes,
    *,
    primary: Recognizer,
    extra_recognizers: Optional[Dict[str, Recognizer]] = None,
    secondary: Optional[Recognizer] = None,
    secondary_lang: str = "en",
    primary_lang: str = "tr",
    default_language: str = "tr",
    auto_switch_model: bool = True,
    dual_decode_margin: float = 0.6,
    prefer_online_detect: bool = True,
    dual_decode_only_if_ambiguous: bool = True,
) -> Tuple[str, str]:
    """Pick the best transcript/language using langdetect + optional multi-model decode."""
    primary_text = str(text or "").strip()
    if not primary_text and not pcm:
        return "", default_language

    extras: Dict[str, Recognizer] = dict(extra_recognizers or {})
    if secondary is not None and secondary_lang and secondary_lang not in extras:
        extras[str(secondary_lang)] = secondary

    if not auto_switch_model or not pcm or not extras:
        lang = (
            _detect_language(primary_text, default=default_language, prefer_online=prefer_online_detect)
            if primary_text
            else default_language
        )
        return primary_text, lang

    if dual_decode_only_if_ambiguous and primary_text:
        detected = _detect_language(primary_text, default=primary_lang, prefer_online=prefer_online_detect)
        primary_score = _transcript_score(primary_text, primary_lang, default_lang=default_language)
        words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ']+", primary_text.lower())
        tr_hits = sum(1 for w in words if w in _TR_STOPWORDS)
        if detected == primary_lang and primary_score >= 3.0 and tr_hits >= 1:
            return primary_text, detected

    candidates: Dict[str, str] = {primary_lang: primary_text}
    for lang, rec in extras.items():
        alt_text = _decode_pcm(rec, pcm)
        if alt_text:
            candidates[str(lang)] = alt_text

    if len(candidates) <= 1 and primary_text:
        lang = _detect_language(primary_text, default=default_language, prefer_online=prefer_online_detect)
        return primary_text, lang

    best_lang = primary_lang
    best_text = primary_text
    best_score = _transcript_score(primary_text, primary_lang, default_lang=default_language) if primary_text else -1.0

    for lang, cand in candidates.items():
        if not cand:
            continue
        score = _transcript_score(cand, lang, default_lang=default_language)
        margin = 0.0 if lang == primary_lang else max(0.0, float(dual_decode_margin)) * 0.5
        if score > best_score + margin:
            best_score = score
            best_lang = lang
            best_text = cand

    if not best_text:
        return primary_text, _detect_language(primary_text or "", default=default_language, prefer_online=prefer_online_detect)

    resolved_lang = _detect_language(best_text, default=best_lang or default_language, prefer_online=prefer_online_detect)
    # Prefer decoder language when detection is ambiguous but decoder won clearly
    if resolved_lang != best_lang and best_score >= 2.0:
        resolved_lang = best_lang.split("-", 1)[0]

    logger.info(
        "STT picked lang=%s (score=%.2f candidates=%s text=%r)",
        resolved_lang,
        best_score,
        list(candidates.keys()),
        best_text[:64],
    )
    return best_text, resolved_lang
