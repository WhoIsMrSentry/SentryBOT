from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.common.persona_scope import DEFAULT_PERSONA_ID, get_active_persona, normalize_persona_id

from .relationship_storage import RelationshipStorageMixin


def _scope_persona(persona_id: Optional[str] = None) -> str:
    if persona_id is not None and str(persona_id).strip():
        return normalize_persona_id(persona_id)
    return get_active_persona()


class RelationshipMemory(RelationshipStorageMixin):
    """Lightweight per-person social memory for companion behavior.

    Backwards-compatible: when a :class:`modules.cognitive_memory.SocialDB` instance is
    registered as the process default, observations and chat lines are routed
    to the shared SQLite store. The original JSON path remains supported and
    serves as the fallback when ``social_db`` is unavailable.
    """

    def __init__(
        self,
        enabled: bool = True,
        path: str = "",
        social_db: Optional[Any] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.path = Path(path).resolve() if path else None
        if social_db is False:
            social_db = None
        elif social_db is None:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self._lock = threading.RLock()
        self._learner = None
        self._people: Dict[str, Dict[str, Any]] = {}
        if self.enabled and self._social_db is None:
            self._load()

    def observe_person(self, name: str, is_owner: bool = False, emotion: str = "") -> None:
        if not self.enabled:
            return
        key = self._normalize(name)
        if not key:
            return
        if self._social_db is not None:
            try:
                self._social_db.persons.upsert(
                    name=name,
                    is_owner=is_owner or None,
                    owner_priority=is_owner or None,
                    last_emotion=emotion or None,
                    increment_seen=True,
                )
                rec = self._social_db.persons.get_by_name(name)
                if rec is not None:
                    self._social_db.sightings.record(
                        person_id=rec["id"],
                        source="autonomy.relationship",
                        mood=emotion or "",
                    )
            except Exception:
                pass
            return
        now = time.time()
        rec = self._people.setdefault(
            key,
            {
                "name": name,
                "first_seen": now,
                "last_seen": 0.0,
                "seen_count": 0,
                "is_owner": False,
                "last_emotion": "",
                "chat_history": [],
                "preferences": {},
                "moments": [],
            },
        )
        rec["name"] = name
        rec["last_seen"] = now
        rec["seen_count"] = int(rec.get("seen_count", 0)) + 1
        rec["is_owner"] = bool(rec.get("is_owner", False) or is_owner)
        if emotion:
            rec["last_emotion"] = str(emotion)
        self._persist()

    def classify_person(self, name: str, *, known_guest_min_seen_count: int = 0) -> str:
        """Return the privacy-safe social type without creating a new person record."""
        key = self._normalize(name)
        if not key:
            return "unknown_guest"
        record: Dict[str, Any] = {}
        if self._social_db is not None:
            try:
                found = self._social_db.persons.get_by_name(name)
                record = dict(found) if isinstance(found, dict) else {}
            except Exception:
                record = {}
        else:
            record = dict(self._people.get(key) or {})
        if bool(record.get("is_owner") or record.get("owner_priority")):
            return "owner"
        seen_count = int(record.get("seen_count") or record.get("sightings_count") or 0)
        if record and seen_count >= max(0, int(known_guest_min_seen_count)):
            return "known_guest"
        return "unknown_guest"

    def _persona_json_bucket(self, rec: Dict[str, Any], persona_id: Optional[str] = None) -> Dict[str, Any]:
        """Return per-persona conversational bucket in JSON mode (`sentry` uses top-level keys)."""
        pid = _scope_persona(persona_id)
        if pid == DEFAULT_PERSONA_ID:
            return rec
        branches = rec.setdefault("persona_memories", {})
        if not isinstance(branches, dict):
            branches = {}
            rec["persona_memories"] = branches
        return branches.setdefault(
            pid,
            {"chat_history": [], "preferences": {}, "moments": []},
        )

    def add_chat(
        self,
        name: str,
        role: str,
        text: str,
        *,
        persona_id: Optional[str] = None,
    ) -> None:
        if not self.enabled:
            return
        key = self._normalize(name)
        text_val = str(text or "").strip()
        if not key or not text_val:
            return
        pid_scope = _scope_persona(persona_id)
        if self._social_db is not None:
            pid = ""
            try:
                with self._social_db.transaction():
                    rec = self._social_db.persons.upsert(name=name, increment_seen=True)
                    pid = str(rec.get("id") or "")
                    if not pid:
                        return
                    self._social_db.sightings.record(
                        person_id=pid,
                        source="autonomy.relationship",
                        mood="",
                    )
                    self._social_db.chat_episodes.append(
                        person_id=pid,
                        role=str(role or "user"),
                        text=text_val[:240],
                        persona_id=pid_scope,
                    )
                    self._social_db.chat_episodes.prune_for_person(
                        pid,
                        keep_last=16,
                        persona_id=pid_scope,
                    )
                    if str(role or "").strip().lower() == "user":
                        self._extract_preferences_db(pid, text_val, persona_id=pid_scope)
                        self._social_db.moments.add_or_boost(
                            person_id=pid,
                            text=f"user:{text_val}",
                            salience=0.35,
                            persona_id=pid_scope,
                        )
            except Exception:
                return
            if pid:
                self._index_chat_rag(pid=pid, role=role, text=text_val, persona_id=pid_scope)
            return
        with self._lock:
            self.observe_person(name=name)
            rec = self._people.get(key)
            if rec is None:
                return
            bucket = self._persona_json_bucket(rec, pid_scope)
            hist = bucket.setdefault("chat_history", [])
            hist.append({"ts": time.time(), "role": str(role or "user"), "text": text_val[:240]})
            if len(hist) > 16:
                del hist[:-16]
            if str(role or "").strip().lower() == "user":
                self._extract_preferences(bucket, text_val)
                self._add_moment(bucket, text=f"user:{text_val}", salience=0.35)
            self._persist()

    def _index_chat_rag(
        self,
        *,
        pid: Any,
        role: Any,
        text: str,
        persona_id: Optional[str] = None,
    ) -> None:
        try:
            from .chat_rag import get_default

            rag = get_default()
            rag.ingest(person_id=str(pid), role=str(role or "user"), text=text, persona_id=persona_id)
            now = time.time()
            if not hasattr(self, "_rag_last_prune") or now - float(getattr(self, "_rag_last_prune", 0.0)) > 600.0:
                self._rag_last_prune = now
                rag.prune()
        except Exception:
            pass

    def recall_chat(
        self,
        name: str,
        query: str,
        limit: int = 6,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            from .chat_rag import get_default

            rec = self.get(name)
            pid = rec.get("id") if isinstance(rec, dict) else ""
            rag = get_default()
            return rag.recall(
                str(query or ""),
                person_id=str(pid or ""),
                limit=limit,
                persona_id=persona_id,
            )
        except Exception:
            return []

    def top_people(self, limit: int = 3) -> List[Dict[str, Any]]:
        if self._social_db is not None:
            try:
                return self._social_db.persons.top_people(limit=limit)
            except Exception:
                return []
        rows = list(self._people.values())
        rows.sort(key=lambda r: (int(r.get("seen_count", 0)), float(r.get("last_seen", 0.0))), reverse=True)
        return rows[: max(1, int(limit))]

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        if self._social_db is not None:
            try:
                return self._social_db.persons.get_by_name(name)
            except Exception:
                return None
        return self._people.get(self._normalize(name))

    def last_user_utterance(self, name: str, *, persona_id: Optional[str] = None) -> str:
        pid_scope = _scope_persona(persona_id)
        if self._social_db is not None:
            rec = self.get(name)
            if not rec:
                return ""
            try:
                return self._social_db.chat_episodes.last_user_utterance(rec["id"], persona_id=pid_scope)
            except Exception:
                return ""
        rec = self.get(name)
        if not rec:
            return ""
        bucket = self._persona_json_bucket(rec, pid_scope)
        hist = bucket.get("chat_history", [])
        if not isinstance(hist, list):
            return ""
        for item in reversed(hist):
            if not isinstance(item, dict):
                continue
            if str(item.get("role", "")).strip().lower() == "user":
                return str(item.get("text", "")).strip()
        return ""

    def recall_candidates(
        self,
        name: str,
        limit: int = 12,
        *,
        persona_id: Optional[str] = None,
    ) -> List[str]:
        """Return past snippets (moments + recent user lines) scoped to the active persona."""
        out: List[str] = []
        pid_scope = _scope_persona(persona_id)
        rec = self.get(name) or {}
        if self._social_db is not None:
            pid = str(rec.get("id") or "") if rec else ""
            if pid:
                try:
                    for m in self._social_db.moments.top_for_person(pid, limit=limit, persona_id=pid_scope):
                        txt = str((m or {}).get("text", "")).strip()
                        if txt:
                            out.append(txt)
                except Exception:
                    pass
            return out[:limit]
        bucket = self._persona_json_bucket(rec, pid_scope) if rec else {}
        moments = bucket.get("moments", []) if isinstance(bucket.get("moments", []), list) else []
        for m in moments:
            txt = str((m or {}).get("text", "")).strip()
            if txt:
                out.append(txt)
        hist = bucket.get("chat_history", []) if isinstance(bucket.get("chat_history", []), list) else []
        for item in reversed(hist):
            if isinstance(item, dict) and str(item.get("role", "")).strip().lower() == "user":
                txt = str(item.get("text", "")).strip()
                if txt and txt not in out:
                    out.append(txt)
            if len(out) >= limit:
                break
        return out[:limit]

    def social_profile(self, name: str, *, persona_id: Optional[str] = None) -> Dict[str, Any]:
        pid_scope = _scope_persona(persona_id)
        if self._social_db is not None:
            rec = self.get(name) or {}
            pid = str(rec.get("id") or "") if rec else ""
            prefs_grouped: Dict[str, List[str]] = {}
            top_memory = ""
            if pid:
                try:
                    prefs_grouped = self._social_db.relationships.list_grouped(pid, persona_id=pid_scope)
                    top = self._social_db.moments.top_for_person(pid, limit=1, persona_id=pid_scope)
                    if top:
                        top_memory = str(top[0].get("text", "")).strip()
                except Exception:
                    pass
            likes = list(prefs_grouped.get("likes", []))
            dislikes = list(prefs_grouped.get("dislikes", []))
            topics = list(prefs_grouped.get("topics", []))
            return {
                "name": (rec.get("display_name") if rec else None) or name,
                "persona_id": pid_scope,
                "is_owner": bool(rec.get("is_owner", False)),
                "seen_count": int(rec.get("seen_count", 0) or 0),
                "trust_score": float(rec.get("trust_score", 0.0) or 0.0),
                "likes": likes[:5],
                "dislikes": dislikes[:5],
                "topics": topics[:6],
                "last_user_utterance": self.last_user_utterance(name, persona_id=pid_scope),
                "top_memory": top_memory[:180],
            }
        with self._lock:
            rec = self.get(name) or {}
            bucket = self._persona_json_bucket(rec, pid_scope) if rec else {}
            prefs = bucket.get("preferences", {}) if isinstance(bucket.get("preferences", {}), dict) else {}
            likes = list(prefs.get("likes", []) if isinstance(prefs.get("likes", []), list) else [])
            dislikes = list(prefs.get("dislikes", []) if isinstance(prefs.get("dislikes", []), list) else [])
            topics = list(prefs.get("topics", []) if isinstance(prefs.get("topics", []), list) else [])
            moments = list(bucket.get("moments", []) if isinstance(bucket.get("moments", []), list) else [])
            top_memory = ""
            if moments:
                moments.sort(key=lambda m: float(m.get("score", 0.0)), reverse=True)
                top_memory = str((moments[0] or {}).get("text", "")).strip()
            return {
                "name": rec.get("name", name),
                "persona_id": pid_scope,
                "is_owner": bool(rec.get("is_owner", False)),
                "seen_count": int(rec.get("seen_count", 0) or 0),
                "trust_score": float(rec.get("trust_score", 0.0) or 0.0),
                "likes": likes[:5],
                "dislikes": dislikes[:5],
                "topics": topics[:6],
                "last_user_utterance": self.last_user_utterance(name, persona_id=pid_scope),
                "top_memory": top_memory[:180],
            }

    def decay_person(self, name: str, *, persona_id: Optional[str] = None) -> int:
        """Explicit maintenance hook to apply moment decay without mutating read queries."""
        if not self.enabled:
            return 0
        pid_scope = _scope_persona(persona_id)
        if self._social_db is not None:
            rec = self.get(name) or {}
            pid = str(rec.get("id") or "")
            if not pid:
                return 0
            return int(self._social_db.moments.decay(pid, persona_id=pid_scope))
        with self._lock:
            rec = self.get(name)
            if not rec:
                return 0
            bucket = self._persona_json_bucket(rec, pid_scope)
            before = len(bucket.get("moments") or [])
            self._decay_moments(bucket)
            after = len(bucket.get("moments") or [])
            self._persist()
            return max(0, before - after)

    def build_social_context(self, current_speaker: str = "") -> str:
        if not self.enabled:
            return ""
        lines: List[str] = []
        top = self.top_people(limit=3)
        if top:
            lines.append("Recent social context:")
        for p in top:
            pname = str(p.get("display_name") or p.get("name") or "Unknown")
            seen = int(p.get("seen_count", 0))
            is_owner = bool(p.get("is_owner", False))
            last_em = str(p.get("last_emotion", "")).strip()
            tag = "owner" if is_owner else "known"
            line = f"- {pname} ({tag}), seen={seen}"
            if last_em:
                line += f", last_emotion={last_em}"
            lines.append(line)
        if current_speaker:
            lines.append(f"Current speaker guess: {current_speaker}")
        return "\n".join(lines).strip()
