"""Memory consolidation: turn raw dialogue into durable, recallable facts.

Episodic memory stores everything flat; this layer mines high-value, long-lived
facts ("my name is …", "I have a dog named …", "I work as …") and persists them
with high importance so semantic recall surfaces them first. When a social_db
handle is available it mirrors facts onto the speaker's relationship record,
bridging the previously disconnected episodic and social memory silos.

NEW (Faz 3): LLM-based fact extraction with semantic categorization into
WorldMemory (people, places, objects, events, observations, habits) for RAG recall.
"""

from __future__ import annotations

# --- SentryBOT memory/world boundary contract ---
MEMORY_WORLD_COMPATIBILITY = True
MEMORY_WORLD_BOUNDARY_ROLE = 'agent_core_memory_consolidator'
MEMORY_WORLD_RUNTIME_OWNER = 'modules.cognitive_memory.services.world_memory'
MEMORY_WORLD_BOUNDARY_REASON = 'MemoryConsolidator now uses LLM extraction and writes to WorldMemory for RAG recall.'
# --- End SentryBOT memory/world boundary contract ---

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent.memory_consolidator")


_FACT_EXTRACTION_PROMPT = """You are a memory extractor for a companion robot. Extract durable, semantic facts from the conversation below.

CATEGORIES (choose the BEST one per fact):
- people: Names, relationships, roles, family members, pets
- places: Locations, rooms, addresses, favorite spots
- objects: Devices, vehicles, possessions, tools
- events: Appointments, recurring activities, past experiences
- observations: Preferences, traits, habits, opinions, health info
- habits: Routines, schedules, repeated behaviors

RULES:
1. Only extract facts that are STABLE and USEFUL for long-term recall (not transient chat).
2. Each fact must be a complete, self-contained sentence.
3. Include the SPEAKER in the fact when relevant (e.g., "Ahmet likes coffee" not "likes coffee").
4. Output ONLY a JSON array of objects: [{"kind": "...", "name": "...", "summary": "...", "properties": {}, "confidence": 0.8, "salience": 0.7, "tags": []}]
5. Skip greetings, filler, questions without answers, and hypotheticals.
6. For Turkish: "benim adım X" -> {"kind": "people", "name": "X", "summary": "User's name is X", ...}
7. For English: "my name is X" -> {"kind": "people", "name": "X", "summary": "User's name is X", ...}
8. Confidence: 0.9 = explicitly stated, 0.7 = strongly implied, 0.5 = uncertain.

CONVERSATION:
{conversation}

FACTS:"""


class MemoryConsolidator:
    def __init__(
        self,
        memory: Any = None,
        social_db: Any = None,
        learner: Any = None,
        autonomy_client: Any = None,
        world_memory: Any = None,
        llm_client: Any = None,
        enabled: bool = True,
    ) -> None:
        self.memory = memory
        self.social_db = social_db
        self._learner = learner
        self.autonomy_client = autonomy_client
        self.world_memory = world_memory
        self.llm_client = llm_client
        self.enabled = enabled
        self._lock = threading.Lock()
        self._pending_queue: List[Dict[str, Any]] = []
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _get_learner(self):
        if self._learner is not None and hasattr(self._learner, "extract_facts"):
            return self._learner
        try:
            from modules.cognitive_memory.services.preference_learner import PreferenceLearner

            self._learner = PreferenceLearner()
        except Exception:
            self._learner = None
        return self._learner

    def extract_facts(self, text: str, speaker: Optional[str] = None) -> List[str]:
        """Extract facts via the shared cognitive_memory PreferenceLearner."""
        learner = self._get_learner()
        if learner is None or not hasattr(learner, "extract_facts"):
            return []
        try:
            return list(learner.extract_facts(text) or [])
        except Exception:
            logger.debug("PreferenceLearner.extract_facts failed", exc_info=True)
            return []

    def extract_facts_llm(self, conversation: str, speaker: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract structured facts using LLM. Returns list of fact dicts for WorldMemory."""
        if not self.llm_client:
            return []
        try:
            # Use replace rather than str.format() so JSON braces in prompt/text never trigger KeyError.
            prompt = _FACT_EXTRACTION_PROMPT.replace("{conversation}", str(conversation))
            # Use the LLM client directly (assumes ollama-compatible interface)
            if hasattr(self.llm_client, "chat"):
                from modules.common.model_roles import DEFAULT_UTILITY_MODEL

                model_name = (
                    getattr(self, "llm_model", None)
                    or getattr(self.llm_client, "model", None)
                    or DEFAULT_UTILITY_MODEL
                )
                resp = self.llm_client.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1, "num_predict": 512, "num_ctx": 8192},
                )
                content = resp.get("message", {}).get("content", "").strip()
            else:
                return []

            # Parse JSON array
            facts = self._parse_facts_json(content)
            # Filter and enrich
            enriched = []
            for f in facts:
                kind = f.get("kind", "observations")
                name = f.get("name", "").strip()
                summary = f.get("summary", "").strip()
                if not name or not summary:
                    continue
                enriched.append({
                    "kind": kind,
                    "name": name,
                    "summary": summary,
                    "properties": f.get("properties", {}),
                    "confidence": float(f.get("confidence", 0.7)),
                    "salience": float(f.get("salience", 0.6)),
                    "tags": f.get("tags", []),
                    "speaker": speaker,
                })
            return enriched
        except Exception as e:
            logger.debug(f"LLM fact extraction failed: {e}")
            return []

    def _parse_facts_json(self, content: str) -> List[Dict[str, Any]]:
        """Extract JSON array from LLM output."""
        # Find JSON array in response
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1 or end < start:
            return []
        json_str = content[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common issues
            try:
                return json.loads(json_str.replace("'", '"'))
            except Exception:
                return []

    def consolidate(self, text: str, speaker: Optional[str] = None) -> List[str]:
        """Consolidate dialogue into episodic memory and WorldMemory."""
        if not self.enabled:
            return []

        # Fast path: regex-based facts for immediate storage
        facts = self.extract_facts(text, speaker)
        for fact in facts:
            self._store_episodic(fact)
            if speaker:
                self._store_social(speaker, fact)

        # Queue for async LLM extraction + WorldMemory write
        if self.llm_client or self.world_memory or self.autonomy_client:
            with self._lock:
                self._pending_queue.append({
                    "text": text,
                    "speaker": speaker,
                    "timestamp": time.time(),
                })
            self._ensure_worker()

        return facts

    def _ensure_worker(self):
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()

    def _process_queue(self):
        while not self._stop_event.is_set():
            item = None
            with self._lock:
                if self._pending_queue:
                    item = self._pending_queue.pop(0)
            if item:
                try:
                    self._consolidate_async(item)
                except Exception as e:
                    logger.debug(f"Async consolidation failed: {e}")
            else:
                # Wait a bit before checking again
                self._stop_event.wait(1.0)

    def _consolidate_async(self, item: Dict[str, Any]):
        """Async LLM extraction + WorldMemory write."""
        text = item.get("text", "")
        speaker = item.get("speaker")

        # Build context from recent dialogue if needed
        context = text
        # Extract structured facts via LLM
        structured_facts = self.extract_facts_llm(context, speaker)

        if not structured_facts:
            return

        # Write to WorldMemory (autonomy's JSON store)
        if self.world_memory:
            for fact in structured_facts:
                try:
                    self.world_memory.observe({
                        "kind": fact["kind"],
                        "name": fact["name"],
                        "summary": fact["summary"],
                        "properties": fact.get("properties", {}),
                        "confidence": fact["confidence"],
                        "salience": fact["salience"],
                        "source": "dialogue_consolidator",
                        "speaker": speaker,
                    }, source="memory_consolidator")
                except Exception as e:
                    logger.debug(f"WorldMemory write failed: {e}")

        # Also push via autonomy client (hits RAG SQLite store)
        if self.autonomy_client:
            observe_fn = getattr(self.autonomy_client, "world_memory_observe", None) or getattr(
                self.autonomy_client, "observe_world_memory", None
            )
            if callable(observe_fn):
                for fact in structured_facts:
                    try:
                        payload = {
                            "kind": fact["kind"],
                            "name": fact["name"],
                            "summary": fact["summary"],
                            "properties": fact.get("properties", {}),
                            "confidence": fact["confidence"],
                            "salience": fact["salience"],
                            "tags": fact.get("tags", []),
                        }
                        try:
                            observe_fn(payload, source="memory_consolidator")
                        except TypeError:
                            observe_fn(payload)
                    except Exception as e:
                        logger.debug(f"Autonomy client WorldMemory write failed: {e}")

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

    def shutdown(self):
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)


__all__ = ["MemoryConsolidator"]