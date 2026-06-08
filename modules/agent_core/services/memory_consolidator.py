"""Memory consolidation: turn raw dialogue into durable, recallable facts.

Episodic memory stores everything flat; this layer mines high-value, long-lived
facts ("my name is …", "I have a dog named …", "I work as …") and persists them
with high importance so semantic recall surfaces them first. When a social_db
handle is available it mirrors facts onto the speaker's relationship record,
bridging the previously disconnected episodic and social memory silos.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

logger = logging.getLogger("agent.memory_consolidator")

# (compiled pattern, fact template). Group 1 is the captured value.
_NAME = r"[A-Za-zÇĞİıÖŞÜçğöşü][A-Za-zÇĞİıÖŞÜçğöşü\-]{1,30}"

_PATTERNS = [
    (re.compile(r"\bben(?:im)?\s+ad[ıi]m\s+(" + _NAME + r")", re.IGNORECASE), "user name is {0}"),
    (re.compile(r"\bismim\s+(" + _NAME + r")", re.IGNORECASE), "user name is {0}"),
    (re.compile(r"\bmy name is\s+(" + _NAME + r")", re.IGNORECASE), "user name is {0}"),
    (re.compile(r"\bi am\s+(" + _NAME + r")(?:\s|$|[.!,])", re.IGNORECASE), "user name is {0}"),
    (re.compile(r"\b(?:k[öo]pe[ğg]im|kedim)(?:in ad[ıi])?\s+(" + _NAME + r")", re.IGNORECASE), "user has a pet named {0}"),
    (re.compile(r"\bmy (?:dog|cat)(?:'s name)? is\s+(" + _NAME + r")", re.IGNORECASE), "user has a pet named {0}"),
    (re.compile(r"\b(?:işim|meslegim|mesle[ğg]im)\s+(" + _NAME + r")", re.IGNORECASE), "user works as {0}"),
    (re.compile(r"\bi work as (?:a |an )?(" + _NAME + r")", re.IGNORECASE), "user works as {0}"),
    (re.compile(r"\b(" + _NAME + r")['’]?(?:de|da|te|ta)\s+(?:oturuyorum|yas[ıi]yorum)", re.IGNORECASE), "user lives in {0}"),
    (re.compile(r"\bi live in\s+(" + _NAME + r")", re.IGNORECASE), "user lives in {0}"),
]


class MemoryConsolidator:
    def __init__(self, memory: Any = None, social_db: Any = None) -> None:
        self.memory = memory
        self.social_db = social_db

    def extract_facts(self, text: str) -> List[str]:
        raw = str(text or "")
        # only mine the user's side of a "User: ... | Bot: ..." line if present
        if "|" in raw:
            raw = raw.split("|", 1)[0]
        raw = re.sub(r"(?i)^\s*user\s*:\s*", "", raw).strip()
        if not raw:
            return []

        facts: List[str] = []
        for pattern, template in _PATTERNS:
            match = pattern.search(raw)
            if match:
                value = match.group(1).strip()
                if value and len(value) > 1:
                    fact = template.format(value)
                    if fact not in facts:
                        facts.append(fact)
        return facts

    def consolidate(self, text: str, speaker: Optional[str] = None) -> List[str]:
        facts = self.extract_facts(text)
        if not facts:
            return []
        for fact in facts:
            self._store_episodic(fact)
            if speaker:
                self._store_social(speaker, fact)
        return facts

    def _store_episodic(self, fact: str) -> None:
        if self.memory is None:
            return
        try:
            self.memory.remember("fact", fact, importance=8)
        except Exception:
            logger.debug("failed to store fact in episodic memory", exc_info=True)

    def _store_social(self, speaker: str, fact: str) -> None:
        if self.social_db is None:
            return
        try:
            person = self.social_db.persons.upsert(name=speaker)
            person_id = getattr(person, "person_id", None) or (person.get("person_id") if isinstance(person, dict) else None)
            if person_id and hasattr(self.social_db, "moments"):
                self.social_db.moments.add_or_boost(person_id, fact)
        except Exception:
            logger.debug("failed to mirror fact into social_db", exc_info=True)


__all__ = ["MemoryConsolidator"]
