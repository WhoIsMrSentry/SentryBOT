from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from modules.voice.speech.services.recognizer import Recognizer

logger = logging.getLogger("speech.stt_language")

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_STOPWORDS = frozenset({
    "ben", "sen", "o", "biz", "siz", "onlar", "bana", "sana", "ona", "bize", "size", "onlara",
    "benim", "senin", "onun", "bizim", "sizin", "onlarin",
    "ve", "veya", "ile", "de", "da", "ki", "mi", "mu", "mü", "mı", "ama", "fakat", "lakin",
    "bu", "şu", "o", "bunlar", "şunlar", "onlar", "burada", "şurada", "orada", "buraya", "oraya",
    "ne", "nasıl", "neden", "niçin", "kim", "hangi", "nerede", "nereye", "nereden", "kaç", "zaman",
    "merhaba", "selam", "günaydın", "iyi", "akşamlar", "geceler", "lütfen", "teşekkür", "sağol",
    "kendini", "tanıt", "anlat", "söyle", "yap", "et", "gel", "git", "bak", "dur", "başla",
    "robot", "sentrybot", "sentry", "emir", "evet", "hayır", "tamam", "olur", "olmaz",
    "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on",
    "var", "yok", "oldu", "oldu mu", "şimdi", "sonra", "önce", "güzel", "kötü", "nasılsın",
})
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


def _detect_language(text: str, *, default: str, prefer_online: bool = True) -> str:
    from modules.voice.speak.services.lang_detect import detect_text_language

    return detect_text_language(text, default=default, prefer_online=prefer_online)


def _transcript_score(text: str, target_lang: str) -> float:
    """Score how well a transcript matches the target language."""
    value = str(text or "").strip()
    if not value:
        return 0.0
    words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ']+", value.lower())
    if not words:
        return 0.0

    tr_chars = sum(1 for ch in value if ch in _TR_CHARS)
    tr_hits = sum(1 for w in words if w in _TR_STOPWORDS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    detected = _detect_language(value, default="tr", prefer_online=True)

    if target_lang.startswith("tr"):
        score = 2.0 if detected == "tr" else 1.0
        score += tr_hits * 1.5
        score += tr_chars * 1.0
        if len(words) >= 2 and tr_hits >= 1:
            score += 2.0
        if detected == "en" and tr_chars == 0 and tr_hits == 0 and en_hits >= 2:
            score -= 2.0
        return score

    if target_lang == "en":
        score = 2.0 if detected == "en" else 0.5
        score += en_hits * 1.5
        if len(words) >= 2 and en_hits >= 1:
            score += 2.0
        if tr_chars >= 1 or tr_hits >= 1:
            score -= 3.0
        return score

    # Generic languages: trust langdetect + transcript length
    score = 2.0 if detected == target_lang else 0.5
    score += min(len(words), 8) * 0.2
    return score


def _decode_pcm(recognizer: Recognizer, pcm: bytes) -> str:
    try:
        return str(recognizer.recognize_pcm(pcm) or "").strip()
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
        primary_score = _transcript_score(primary_text, primary_lang)
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
    best_score = _transcript_score(primary_text, primary_lang) if primary_text else -1.0

    for lang, cand in candidates.items():
        if not cand:
            continue
        score = _transcript_score(cand, lang)
        if score > best_score + (0.0 if lang == primary_lang else dual_decode_margin * 0.5):
            best_score = score
            best_lang = lang
            best_text = cand
        elif score > best_score:
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
