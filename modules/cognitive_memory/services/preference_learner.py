"""Config-driven extraction of durable facts and social preferences from chat.

Single source for regex patterns used by :class:`MemoryConsolidator` and
:class:`RelationshipMemory`, so the companion learning loop does not maintain
duplicate pattern lists in two modules.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_NAME = r"[A-Za-zÇĞİıÖŞÜçğöşü][A-Za-zÇĞİıÖŞÜçğöşü\-]{1,30}"

_DEFAULT_FACT_PATTERNS: List[Tuple[str, str]] = [
    (r"\bben(?:im)?\s+ad[ıi]m\s+(" + _NAME + r")", "user name is {0}"),
    (r"\bismim\s+(" + _NAME + r")", "user name is {0}"),
    (r"\bmy name is\s+(" + _NAME + r")", "user name is {0}"),
    (r"\bi am\s+(" + _NAME + r")(?:\s|$|[.!,])", "user name is {0}"),
    (r"\b(?:k[öo]pe[ğg]im|kedim)(?:in ad[ıi])?\s+(" + _NAME + r")", "user has a pet named {0}"),
    (r"\bmy (?:dog|cat)(?:'s name)? is\s+(" + _NAME + r")", "user has a pet named {0}"),
    (r"\b(?:işim|meslegim|mesle[ğg]im)\s+(" + _NAME + r")", "user works as {0}"),
    (r"\bi work as (?:a |an )?(" + _NAME + r")", "user works as {0}"),
    (r"\b(" + _NAME + r")['']?(?:de|da|te|ta)\s+(?:oturuyorum|yas[ıi]yorum)", "user lives in {0}"),
    (r"\bi live in\s+(" + _NAME + r")", "user lives in {0}"),
]

_DEFAULT_LIKE_PATTERNS = [
    r"\b(?:seviyorum|hoslaniyorum|bayiliyorum)\s+([a-z0-9_\-\sçğıöşü]{2,40})",
    r"\b(?:i like|i love)\s+([a-z0-9_\-\s]{2,40})",
    r"\b(?:favorim|favorite)\s+([a-z0-9_\-\s]{2,40})",
]

_DEFAULT_DISLIKE_PATTERNS = [
    r"\b(?:sevmiyorum|nefret ediyorum)\s+([a-z0-9_\-\sçğıöşü]{2,40})",
    r"\b(?:i hate|i dislike)\s+([a-z0-9_\-\s]{2,40})",
]

_DEFAULT_TOPIC_TOKENS = [
    "muzik", "film", "oyun", "okul", "is", "hava", "spor", "robot", "yazilim", "ai",
]


class PreferenceLearner:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config if isinstance(config, dict) else {}
        self._fact_patterns = self._compile_fact_patterns(cfg.get("fact_patterns"))
        self._like_patterns = self._compile_list(cfg.get("like_patterns"), _DEFAULT_LIKE_PATTERNS)
        self._dislike_patterns = self._compile_list(cfg.get("dislike_patterns"), _DEFAULT_DISLIKE_PATTERNS)
        self._topic_tokens = list(cfg.get("topic_tokens") or _DEFAULT_TOPIC_TOKENS)

    @staticmethod
    def _compile_fact_patterns(raw) -> List[Tuple[re.Pattern, str]]:
        if isinstance(raw, list) and raw:
            out = []
            for item in raw:
                if isinstance(item, dict) and item.get("pattern") and item.get("template"):
                    out.append((re.compile(str(item["pattern"]), re.IGNORECASE), str(item["template"])))
            if out:
                return out
        return [(re.compile(p, re.IGNORECASE), t) for p, t in _DEFAULT_FACT_PATTERNS]

    @staticmethod
    def _compile_list(raw, defaults: List[str]) -> List[re.Pattern]:
        src = raw if isinstance(raw, list) and raw else defaults
        return [re.compile(str(p), re.IGNORECASE) for p in src]

    def extract_facts(self, text: str) -> List[str]:
        raw = self._user_only(text)
        if not raw:
            return []
        facts: List[str] = []
        for pattern, template in self._fact_patterns:
            match = pattern.search(raw)
            if match:
                value = match.group(1).strip()
                if value and len(value) > 1:
                    fact = template.format(value)
                    if fact not in facts:
                        facts.append(fact)
        return facts

    def extract_preferences(self, text: str) -> Dict[str, List[str]]:
        low = str(text or "").strip().lower()
        likes: List[str] = []
        dislikes: List[str] = []
        topics: List[str] = []
        if not low:
            return {"likes": likes, "dislikes": dislikes, "topics": topics}

        for pat in self._like_patterns:
            for m in pat.findall(low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in likes:
                    likes.append(val)

        for pat in self._dislike_patterns:
            for m in pat.findall(low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in dislikes:
                    dislikes.append(val)

        if "?" in low:
            for token in self._topic_tokens:
                if token in low and token not in topics:
                    topics.append(token)

        return {"likes": likes, "dislikes": dislikes, "topics": topics}

    @staticmethod
    def _user_only(text: str) -> str:
        raw = str(text or "")
        if "|" in raw:
            raw = raw.split("|", 1)[0]
        return re.sub(r"(?i)^\s*user\s*:\s*", "", raw).strip()


__all__ = ["PreferenceLearner"]
