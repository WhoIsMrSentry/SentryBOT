"""Memory consolidation: turn raw dialogue into durable, recallable facts.

Episodic memory stores everything flat; this layer mines high-value, long-lived
facts ("my name is …", "I have a dog named …", "I work as …") and persists them
with high importance so semantic recall surfaces them first. When a social_db
handle is available it mirrors facts onto the speaker's relationship record,
bridging the previously disconnected episodic and social memory silos.
"""

from __future__ import annotations

# --- SentryBOT memory/world boundary contract ---
MEMORY_WORLD_COMPATIBILITY = True
MEMORY_WORLD_BOUNDARY_ROLE = 'agent_core_compat_memory_consolidator'
MEMORY_WORLD_RUNTIME_OWNER = 'modules.autonomy.services.world_memory'
MEMORY_WORLD_BOUNDARY_REASON = 'MemoryConsolidator is still used by AgentOrchestrator; keep it as compatibility/bridge until consolidation is migrated.'
# --- End SentryBOT memory/world boundary contract ---

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent.memory_consolidator")


class MemoryConsolidator:
    def __init__(self, memory: Any = None, social_db: Any = None, learner: Any = None) -> None:
        self.memory = memory
        self.social_db = social_db
        self._learner = learner

    def _get_learner(self):
        if self._learner is not None:
            return self._learner
        try:
            from modules.autonomy.services.preference_learner import PreferenceLearner

            self._learner = PreferenceLearner()
        except Exception:
            self._learner = None
        return self._learner

    def extract_facts(self, text: str) -> List[str]:
        learner = self._get_learner()
        if learner is not None:
            return learner.extract_facts(text)
        return []

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
            person_id = None
            if isinstance(person, dict):
                person_id = person.get("id") or person.get("person_id")
            else:
                person_id = getattr(person, "id", None) or getattr(person, "person_id", None)
            if person_id and hasattr(self.social_db, "moments"):
                self.social_db.moments.add_or_boost(person_id, fact, salience=0.75)
        except Exception:
            logger.debug("failed to mirror fact into social_db", exc_info=True)


__all__ = ["MemoryConsolidator"]
