"""Extended person identity and memory for SentryBOT.

Wraps existing PeopleMemory and FaceManager with recognition levels (0-5),
relationship tracking, and persistent JSON storage.

Recognition levels:
  0 = unknown
  1 = seen before (low confidence)
  2 = familiar / recurring
  3 = friend
  4 = family / inner circle
  5 = owner
"""

from __future__ import annotations
VLM_PERSON_IDENTITY_COMPATIBILITY_CONTRACT = True
VLM_PERSON_IDENTITY_ROLE = "social_db_primary_person_json_compatibility_store"


import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vlm_bridge.person_identity")

_DEFAULT_STORE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "person_identity.json"
)

RECOGNITION_LABELS = {
    0: "unknown",
    1: "seen_before",
    2: "familiar",
    3: "friend",
    4: "family",
    5: "owner",
}

RELATIONSHIP_TYPES = frozenset({
    "owner", "family", "friend", "known", "stranger", "unknown",
})


@dataclass
class PersonMemoryRecord:
    person_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = "Unknown"
    recognition_level: int = 0
    relationship: str = "unknown"
    face_descriptors: List[Dict[str, Any]] = field(default_factory=list)
    appearance_notes: List[str] = field(default_factory=list)
    voice_notes: List[str] = field(default_factory=list)
    conversation_notes: List[str] = field(default_factory=list)
    last_seen: str = ""
    first_seen: str = ""
    seen_count: int = 0
    trust_score: float = 0.0
    owner_priority: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PersonMemoryRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


class PersonIdentityManager:
    """Manages person recognition, relationship levels, and persistence.

    Thread-safe. Wraps existing FaceManager/PeopleMemory without breaking them.

    When a :class:`modules.social_db.SocialDB` instance is supplied (or registered
    as the process default), writes are persisted to the shared SQLite store
    instead of the compatibility JSON file. The in-memory cache mirrors the database
    rows for fast reads.
    """

    def __init__(
        self,
        store_path: str = "",
        face_manager: Optional[Any] = None,
        people_memory: Optional[Any] = None,
        social_db: Optional[Any] = None,
    ) -> None:
        self._store_path = store_path or _DEFAULT_STORE
        self._face_manager = face_manager
        self._people_memory = people_memory
        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self._lock = threading.Lock()
        self._records: Dict[str, PersonMemoryRecord] = {}
        self._name_index: Dict[str, str] = {}  # name.lower() -> person_id
        self._load()

    # ── Public API ────────────────────────────────────────────────────

    def recognize(
        self, name: str, confidence: float = 0.0, face_score: float = 0.0,
    ) -> PersonMemoryRecord:
        """Look up or create a person record by name."""
        with self._lock:
            name_key = name.strip().lower() if name else "unknown"
            pid = self._name_index.get(name_key)
            if pid and pid in self._records:
                rec = self._records[pid]
                rec.seen_count += 1
                rec.last_seen = time.strftime("%Y-%m-%dT%H:%M:%S")
                if confidence > 0:
                    rec.trust_score = min(1.0, rec.trust_score * 0.9 + confidence * 0.1)
                if face_score > 0:
                    rec.face_descriptors.append({
                        "score": float(face_score),
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    if len(rec.face_descriptors) > 50:
                        rec.face_descriptors = rec.face_descriptors[-50:]
                self._auto_upgrade_level(rec)
                self._save_unlocked()
                return rec

            # New person
            rec = PersonMemoryRecord(
                name=name.strip() if name else "Unknown",
                recognition_level=0,
                relationship="unknown",
                first_seen=time.strftime("%Y-%m-%dT%H:%M:%S"),
                last_seen=time.strftime("%Y-%m-%dT%H:%M:%S"),
                seen_count=1,
                trust_score=min(1.0, confidence),
            )
            self._records[rec.person_id] = rec
            if name_key != "unknown":
                self._name_index[name_key] = rec.person_id
            self._save_unlocked()
            return rec

    def remember_person(
        self, name: str, relationship: str = "", recognition_level: int = -1,
    ) -> PersonMemoryRecord:
        """Store or update a person's relationship and level."""
        with self._lock:
            name_key = name.strip().lower()
            pid = self._name_index.get(name_key)
            if pid and pid in self._records:
                rec = self._records[pid]
            else:
                rec = PersonMemoryRecord(
                    name=name.strip(),
                    first_seen=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    last_seen=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                self._records[rec.person_id] = rec
                self._name_index[name_key] = rec.person_id

            if relationship and relationship in RELATIONSHIP_TYPES:
                rec.relationship = relationship
            if recognition_level >= 0:
                rec.recognition_level = max(0, min(5, recognition_level))
            if rec.recognition_level >= 5:
                rec.owner_priority = True
                rec.relationship = "owner"

            self._save_unlocked()
            return rec

    def update_relationship(
        self, person_id: str, relationship: str = "", recognition_level: int = -1,
    ) -> Optional[PersonMemoryRecord]:
        with self._lock:
            rec = self._records.get(person_id)
            if not rec:
                return None
            if relationship and relationship in RELATIONSHIP_TYPES:
                rec.relationship = relationship
            if recognition_level >= 0:
                rec.recognition_level = max(0, min(5, recognition_level))
            if rec.recognition_level >= 5:
                rec.owner_priority = True
                rec.relationship = "owner"
            self._save_unlocked()
            return rec

    def append_conversation_note(self, person_id: str, text: str) -> bool:
        with self._lock:
            rec = self._records.get(person_id)
            if not rec:
                return False
            line = str(text or "").strip()
            if not line:
                return False
            rec.conversation_notes.append(line)
            if len(rec.conversation_notes) > 100:
                rec.conversation_notes = rec.conversation_notes[-100:]
            if self._social_db is not None:
                try:
                    self._social_db.chat_episodes.append(
                        person_id=person_id,
                        role="note",
                        text=line,
                    )
                except Exception as exc:
                    logger.debug("chat_episodes append failed: %s", exc)
                return True
            self._save_unlocked()
            return True

    def set_owner(self, name: str) -> PersonMemoryRecord:
        """Manually assign owner status to a person."""
        return self.remember_person(name, relationship="owner", recognition_level=5)

    def get_person(self, name: str) -> Optional[PersonMemoryRecord]:
        with self._lock:
            pid = self._name_index.get(name.strip().lower())
            if pid:
                return self._records.get(pid)
            return None

    def get_by_id(self, person_id: str) -> Optional[PersonMemoryRecord]:
        with self._lock:
            return self._records.get(person_id)

    def list_people(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._records.values()]

    def get_owner(self) -> Optional[PersonMemoryRecord]:
        with self._lock:
            for rec in self._records.values():
                if rec.owner_priority or rec.recognition_level >= 5:
                    return rec
            return None

    def is_owner(self, name: str) -> bool:
        rec = self.get_person(name)
        return rec is not None and rec.recognition_level >= 5

    def add_note(self, name: str, note: str, category: str = "appearance") -> None:
        with self._lock:
            pid = self._name_index.get(name.strip().lower())
            rec = self._records.get(pid) if pid else None
            if not rec:
                return
            target = getattr(rec, f"{category}_notes", None)
            if isinstance(target, list):
                target.append(note)
                if len(target) > 20:
                    target[:] = target[-20:]
            self._save_unlocked()

    # ── Internal ──────────────────────────────────────────────────────

    def _auto_upgrade_level(self, rec: PersonMemoryRecord) -> None:
        """Auto-promote recognition level based on seen_count."""
        if rec.recognition_level >= 5:
            return
        if rec.seen_count >= 50 and rec.recognition_level < 2:
            rec.recognition_level = 2
        elif rec.seen_count >= 10 and rec.recognition_level < 1:
            rec.recognition_level = 1

    def _load(self) -> None:
        if self._social_db is not None:
            try:
                rows = self._social_db.persons.list_all()
            except Exception as exc:
                logger.warning("Failed to read persons from social_db: %s", exc)
                rows = []
            for row in rows:
                rec = PersonMemoryRecord(
                    person_id=str(row.get("id") or ""),
                    name=str(row.get("display_name") or "Unknown"),
                    recognition_level=int(row.get("recognition_level") or 0),
                    relationship=str(row.get("relationship") or "unknown"),
                    seen_count=int(row.get("seen_count") or 0),
                    trust_score=float(row.get("trust_score") or 0.0),
                    owner_priority=bool(row.get("owner_priority")),
                )
                extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                if isinstance(extra, dict):
                    rec.appearance_notes = list(extra.get("appearance_notes", []))
                    rec.voice_notes = list(extra.get("voice_notes", []))
                    rec.first_seen = str(extra.get("first_seen", "") or "")
                    rec.last_seen = str(extra.get("last_seen", "") or "")
                    rec.extra = {k: v for k, v in extra.items() if k not in {"appearance_notes", "voice_notes", "first_seen", "last_seen"}}
                if rec.person_id:
                    self._records[rec.person_id] = rec
                    name_key = rec.name.strip().lower()
                    if name_key and name_key != "unknown":
                        self._name_index[name_key] = rec.person_id
            logger.info("Loaded %d person records from social_db", len(self._records))
            return

        try:
            if os.path.exists(self._store_path):
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for pid, d in data.items():
                        if isinstance(d, dict):
                            rec = PersonMemoryRecord.from_dict(d)
                            rec.person_id = pid
                            self._records[pid] = rec
                            name_key = rec.name.strip().lower()
                            if name_key and name_key != "unknown":
                                self._name_index[name_key] = pid
                logger.info("Loaded %d person records from %s", len(self._records), self._store_path)
        except Exception as exc:
            logger.warning("Failed to load person identity store: %s", exc)

    def _save_unlocked(self) -> None:
        if self._social_db is not None:
            try:
                for rec in self._records.values():
                    extra = dict(rec.extra or {})
                    extra.setdefault("appearance_notes", list(rec.appearance_notes))
                    extra.setdefault("voice_notes", list(rec.voice_notes))
                    extra.setdefault("first_seen", rec.first_seen)
                    extra.setdefault("last_seen", rec.last_seen)
                    self._social_db.persons.upsert(
                        name=rec.name,
                        person_id=rec.person_id,
                        recognition_level=int(rec.recognition_level),
                        relationship=str(rec.relationship),
                        is_owner=bool(rec.owner_priority) or int(rec.recognition_level) >= 5,
                        owner_priority=bool(rec.owner_priority),
                        trust_score=float(rec.trust_score),
                        extra_patch=extra,
                    )
            except Exception as exc:
                logger.warning("Failed to persist persons to social_db: %s", exc)
            return

        try:
            os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
            data = {pid: r.to_dict() for pid, r in self._records.items()}
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save person identity store: %s", exc)

    def save(self) -> None:
        with self._lock:
            self._save_unlocked()


# Alias for backward-compatible imports
PersonIdentity = PersonIdentityManager

__all__ = ["PersonIdentityManager", "PersonIdentity", "PersonMemoryRecord", "RECOGNITION_LABELS"]
