from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger("speak.lang_detect")

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_STOPWORDS = frozenset({
    "ben", "sen", "o", "biz", "siz", "onlar", "bu", "şu", "su", "şunlar", "bunlar",
    "bir", "iki", "üç", "uc", "dört", "dort", "beş", "bes", "altı", "alti", "yedi", "sekiz", "dokuz", "on",
    "ve", "veya", "ile", "de", "da", "ki", "mi", "mı", "mu", "mü", "ya", "hem", "ama", "fakat", "ancak", "lakin",
    "için", "icin", "gibi", "kadar", "daha", "çok", "cok", "az", "en", "her", "hiç", "hic", "hepsi",
    "var", "yok", "olur", "olmaz", "oldu", "olabilir", "değil", "degil",
    "merhaba", "selam", "selamlar", "evet", "hayır", "hayir", "tamam", "peki", "tabii", "eyvallah", "oldu",
    "nasıl", "nasil", "nasılsın", "nasilsin", "neden", "niçin", "nicin", "ne", "kim", "kimsin", "nesin",
    "nerede", "nerde", "nereye", "nereden", "neredesin", "hangi", "kaç", "kac", "zaman", "nedir", "kimdir",
    "bunu", "şunu", "sunu", "onu", "bana", "sana", "ona", "bize", "size", "onlara",
    "burada", "burda", "şurada", "orada", "orda", "buraya", "oraya",
    "benim", "senin", "onun", "bizim", "sizin", "onların", "onlarin",
    "yap", "yapsana", "et", "ol", "gel", "git", "bak", "gör", "gor", "bil", "dur", "kalk", "otur", "bekle",
    "aç", "ac", "kapat", "yak", "söndür", "sondur", "dinle", "sus", "konuş", "konus", "anlat", "söyle", "soyle",
    "kendini", "tanıt", "tanit", "yardım", "yardim", "eder", "edebilir", "edebilirim", "yapabilirim",
    "istiyorum", "ediyorum", "bakıyorum", "bakiyorum", "dinliyorum", "bekliyorum", "bilmiyorum", "gidiyor",
    "anladım", "anladim", "hazırım", "hazirim", "iyiyim", "buradayım", "buradayim", "seviyorum",
    "teşekkür", "tesekkur", "teşekkürler", "tesekkurler", "sağol", "sagol", "özür", "ozur", "lütfen", "lutfen",
    "biraz", "şimdi", "simdi", "hemen", "sonra", "önce", "once", "bugün", "bugun", "yarın", "yarin",
    "saat", "hava", "durumu", "haber", "haberler", "gün", "gun", "akşam", "aksam", "sabah", "gece",
    "adım", "adim", "ismim", "ismin", "robotum", "yoldaş", "yoldas",
    "merak", "mutlu", "mutluyum", "sinirli", "sinirlen", "sinirliyim", "kızgın", "kizgin", "korkuyorum",
    "üzgün", "uzgun", "üzgünüm", "uzgunum", "sakin", "sakinleş", "şaşır", "sıkıl",
    "güzel", "guzel", "kötü", "kotu", "harika", "süper", "super", "günaydın", "gunaydin",
    "akşamlar", "aksamlar", "geceler", "hoş", "hos", "geldin", "görüşürüz", "gorusuruz",
    "ışık", "isik", "ışıkları", "isiklari", "renk", "mavi", "kırmızı", "kirmizi", "yeşil", "yesil",
    "sarı", "sari", "mor", "beyaz", "lazer", "ses", "sesi", "türkçe", "turkce", "ingilizce",
})
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
    "introduce", "yourself", "assist", "help", "name", "weather", "today", "check",
    "time", "explain", "search",
    "i'm", "i've", "i'll", "i'd", "you're", "you've", "you'll", "you'd",
    "he's", "she's", "it's", "we're", "we've", "we'll", "they're", "they've", "they'll",
    "that's", "what's", "who's", "there's", "here's",
    "don't", "doesn't", "didn't", "can't", "couldn't", "won't", "wouldn't", "shouldn't",
    "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't",
})
# Single-letter or cross-language interjection tokens that must NOT tip short ambiguous STT snippets to EN
_WEAK_EN_TOKENS = frozenset({"a", "i", "oh", "ah", "um", "uh", "ok", "okay", "hey"})
_TR_MORPH_RE = re.compile(
    r"(?:"
    r"yor(?:um|sun|uz|sunuz)?|"
    r"m[ıiuü]y?or(?:um|sun|uz)?|"
    r"[ae]c[ae][ğgk](?:[ıi]m|s[ıi]n)?|"
    r"s[ıiuü]n[ıiuü]z|"
    r"m[ıiuü]s[ıiuü]n(?:[ıiuü]z)?|"
    r"abilir(?:im|sin|iz)?|"
    r"ebili?r(?:im|sin|iz)?|"
    r"m[ıiuü][şs](?:t[ıiuü]r)?"
    r")$"
)


def count_turkish_morph_hits(words: Iterable[str]) -> int:
    """Count words carrying unambiguous Turkish verb/question suffixes (ASCII-safe)."""
    hits = 0
    for w in words:
        lw = str(w or "").strip().lower()
        if len(lw) >= 4 and _TR_MORPH_RE.search(lw):
            hits += 1
    return hits

try:
    from langdetect import detect as _detect_lang  # type: ignore
    from langdetect import DetectorFactory  # type: ignore

    DetectorFactory.seed = 0
except Exception:
    _detect_lang = None  # type: ignore


def normalize_lang(lang: Optional[str], fallback: str = "tr") -> str:
    raw = str(lang or "").strip().lower().replace("_", "-")
    if not raw or raw == "auto":
        return fallback
    if "-" in raw:
        raw = raw.split("-", 1)[0]
    return raw


def detect_text_language(text: str, *, default: str = "tr", prefer_online: bool = True) -> str:
    """Offline heuristic + optional local langdetect language tag for TTS/STT routing."""
    value = str(text or "").strip()
    if not value:
        return normalize_lang(default)

    tr_chars = sum(1 for ch in value if ch in _TR_CHARS)
    words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ']+", value.lower())
    tr_hits = sum(1 for w in words if w in _TR_STOPWORDS)
    tr_morph = count_turkish_morph_hits(words)
    tr_evidence = tr_hits + tr_morph
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    strong_en_hits = sum(1 for w in words if w in _EN_STOPWORDS and w not in _WEAK_EN_TOKENS)

    if tr_chars >= 2:
        return "tr"
    if tr_chars >= 1 and tr_evidence >= strong_en_hits:
        return "tr"
    if tr_evidence > strong_en_hits:
        return "tr"
    if strong_en_hits > tr_evidence and (
        strong_en_hits >= 2
        or (tr_chars == 0 and tr_evidence == 0 and len(words) <= 3)
    ):
        return "en"
    if en_hits >= 2 and strong_en_hits >= 1 and tr_chars == 0 and tr_evidence == 0:
        return "en"
    if tr_chars >= 1:
        return "tr"

    if prefer_online and _detect_lang is not None and len(words) >= 5 and tr_chars == 0 and tr_evidence == 0:
        try:
            detected = normalize_lang(str(_detect_lang(value)), fallback=default)
            if detected in {"tr", "en"}:
                return detected
        except Exception as exc:
            logger.debug("langdetect failed: %s", exc)

    return normalize_lang(default)


def resolve_speak_language(
    text: str,
    *,
    explicit: Optional[str] = None,
    default: str = "tr",
    prefer_text: bool = True,
) -> str:
    """Pick language for Piper voice: spoken text wins when evidence exists, else explicit."""
    explicit_norm = normalize_lang(explicit, fallback=default)
    if not explicit or not str(explicit).strip():
        return detect_text_language(text, default=default)
    if not prefer_text:
        return explicit_norm
    detected = detect_text_language(text, default="__unknown__")
    if detected and detected != "__unknown__":
        return detected
    return explicit_norm


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
