from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Tuple

WAKE_PHRASES: Tuple[str, ...] = (
    "hey mycroft",
    "mycroft",
    "hey sentrybot",
    "hey sentry",
    "sentrybot",
    "sentry",
)

# Unambiguous phonetic mis-transcriptions of "hey mycroft" / "mycroft" across EN/TR STT
UNAMBIGUOUS_PHONETIC_WAKE_PHRASES: Tuple[str, ...] = (
    "hey my craft",
    "my craft",
    "hey maykroft",
    "ey maykroft",
    "maykroft",
    "hey maykıroft",
    "maykıroft",
    "hey mikrost",
    "mikrost",
    "hey micraft",
    "micraft",
)

# Common Google EN/TR STT hallucinations specifically produced by saying "Hey Mycroft".
# Matched ONLY as whole/leading wake echoes (or within a short post-wakeword window).
CONTEXTUAL_PHONETIC_WAKE_PHRASES: Tuple[str, ...] = (
    "hey minecraft",
    "ey minecraft",
    "play minecraft",
    "minecraft",
    "a microsoft",
    "hey microsoft",
    "my microsoft",
    "hi microsoft",
    "microsoft",
    "am i correct",
    "hey my god",
    "ey my god",
)

_ALL_EXACT_PHRASES = WAKE_PHRASES + UNAMBIGUOUS_PHONETIC_WAKE_PHRASES
_WAKE_PHRASE_RE = re.compile(
    r"(?:^|\b)(?:"
    + "|".join(re.escape(p) for p in sorted(_ALL_EXACT_PHRASES, key=len, reverse=True))
    + r")(?:\b|$)",
    re.IGNORECASE,
)
_CONTEXTUAL_PREFIX_RE = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(p)
        for p in sorted(
            _ALL_EXACT_PHRASES + CONTEXTUAL_PHONETIC_WAKE_PHRASES,
            key=len,
            reverse=True,
        )
    )
    + r")[\s,.:;!?-]*",
    re.IGNORECASE,
)
_EXACT_PREFIX_RE = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(p) for p in sorted(_ALL_EXACT_PHRASES, key=len, reverse=True))
    + r")[\s,.:;!?-]*",
    re.IGNORECASE,
)


def _normalize_phonetic(text: str) -> str:
    low = str(text or "").strip().lower()
    low = re.sub(r"[^\w\sçğıöşü]", " ", low)
    return " ".join(low.split())


def contains_wakeword(text: str, *, include_phonetic: bool = False) -> bool:
    lowered = _normalize_phonetic(text)
    if not lowered:
        return False
    phrases = _ALL_EXACT_PHRASES + (CONTEXTUAL_PHONETIC_WAKE_PHRASES if include_phonetic else ())
    return any(re.search(rf"(?:^|\b){re.escape(p)}(?:\b|$)", lowered) for p in phrases)


def strip_wakewords(text: str, *, include_phonetic: bool = False) -> str:
    lowered = str(text or "").strip().lower()
    phrases = _ALL_EXACT_PHRASES + (CONTEXTUAL_PHONETIC_WAKE_PHRASES if include_phonetic else ())
    for phrase in sorted(phrases, key=len, reverse=True):
        lowered = re.sub(rf"(?:^|\b){re.escape(phrase)}(?:\b|$)", " ", lowered, flags=re.IGNORECASE)
    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.:;!?-")
    return " ".join(lowered.split())


def strip_wakeword_prefix(text: str, *, include_phonetic: bool = False) -> str:
    """Strip one or more leading wakeword (or post-wake phonetic variant) prefixes, preserving remainder."""
    out = str(text or "").strip()
    pattern = _CONTEXTUAL_PREFIX_RE if include_phonetic else _EXACT_PREFIX_RE
    while out:
        nxt = pattern.sub("", out, count=1).lstrip(" ,.:;!?-").strip()
        if nxt == out:
            break
        out = nxt
    return out


def is_wakeword_echo_transcript(
    text: str,
    *,
    wakeword: str = "",
    recent_wakeword: bool = False,
) -> bool:
    """True when transcript is only a wakeword or an openWakeWord phonetic echo."""
    norm = _normalize_phonetic(text)
    if not norm:
        return False

    rem_exact = strip_wakewords(norm, include_phonetic=False)
    extra = _normalize_phonetic(wakeword)
    if extra:
        rem_exact = _normalize_phonetic(rem_exact.replace(extra, " "))
    if len(rem_exact) < 2:
        return True

    if not recent_wakeword:
        return False

    rem_phonetic = strip_wakewords(norm, include_phonetic=True)
    if extra:
        rem_phonetic = _normalize_phonetic(rem_phonetic.replace(extra, " "))
    if len(rem_phonetic) < 2:
        return True

    words = norm.split()
    if len(words) <= 3:
        for target in ("hey mycroft", "mycroft", "hey sentry", "hey sentrybot"):
            if SequenceMatcher(None, norm, target).ratio() >= 0.72:
                return True
    return False
