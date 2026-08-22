from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .relationship_storage import RelationshipStorageMixin


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
        if social_db is None:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
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

    def add_chat(self, name: str, role: str, text: str) -> None:
        if not self.enabled:
            return
        key = self._normalize(name)
        text_val = str(text or "").strip()
        if not key or not text_val:
            return
        if self._social_db is not None:
            try:
                self.observe_person(name=name)
                rec = self._social_db.persons.get_by_name(name)
                if rec is None:
                    return
                pid = rec["id"]
                self._social_db.chat_episodes.append(
                    person_id=pid,
                    role=str(role or "user"),
                    text=text_val[:240],
                )
                self._social_db.chat_episodes.prune_for_person(pid, keep_last=16)
                if str(role or "").strip().lower() == "user":
                    self._extract_preferences_db(pid, text_val)
                    self._social_db.moments.add_or_boost(
                        person_id=pid,
                        text=f"user:{text_val}",
                        salience=0.35,
                    )
            except Exception:
                pass
            return
        self.observe_person(name=name)
        rec = self._people.get(key)
        if rec is None:
            return
        hist = rec.setdefault("chat_history", [])
        hist.append({"ts": time.time(), "role": str(role or "user"), "text": text_val[:240]})
        if len(hist) > 16:
            del hist[:-16]
        if str(role or "").strip().lower() == "user":
            self._extract_preferences(rec, text_val)
            self._add_moment(rec, text=f"user:{text_val}", salience=0.35)
        self._persist()

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

    def last_user_utterance(self, name: str) -> str:
        if self._social_db is not None:
            rec = self.get(name)
            if not rec:
                return ""
            try:
                return self._social_db.chat_episodes.last_user_utterance(rec["id"])
            except Exception:
                return ""
        rec = self.get(name)
        if not rec:
            return ""
        hist = rec.get("chat_history", [])
        if not isinstance(hist, list):
            return ""
        for item in reversed(hist):
            if not isinstance(item, dict):
                continue
            if str(item.get("role", "")).strip().lower() == "user":
                return str(item.get("text", "")).strip()
        return ""

    def recall_candidates(self, name: str, limit: int = 12) -> List[str]:
        """Return past snippets (moments + recent user lines) for relevance recall."""
        out: List[str] = []
        rec = self.get(name) or {}
        if self._social_db is not None:
            pid = str(rec.get("id") or "") if rec else ""
            if pid:
                try:
                    for m in self._social_db.moments.top_for_person(pid, limit=limit):
                        txt = str((m or {}).get("text", "")).strip()
                        if txt:
                            out.append(txt)
                except Exception:
                    pass
        else:
            moments = rec.get("moments", []) if isinstance(rec.get("moments", []), list) else []
            for m in moments:
                txt = str((m or {}).get("text", "")).strip()
                if txt:
                    out.append(txt)
        hist = rec.get("chat_history", []) if isinstance(rec.get("chat_history", []), list) else []
        for item in reversed(hist):
            if isinstance(item, dict) and str(item.get("role", "")).strip().lower() == "user":
                txt = str(item.get("text", "")).strip()
                if txt and txt not in out:
                    out.append(txt)
            if len(out) >= limit:
                break
        return out[:limit]

    def social_profile(self, name: str) -> Dict[str, Any]:
        if self._social_db is not None:
            rec = self.get(name) or {}
            pid = str(rec.get("id") or "") if rec else ""
            prefs_grouped: Dict[str, List[str]] = {}
            top_memory = ""
            if pid:
                try:
                    prefs_grouped = self._social_db.relationships.list_grouped(pid)
                    self._social_db.moments.decay(pid)
                    top = self._social_db.moments.top_for_person(pid, limit=1)
                    if top:
                        top_memory = str(top[0].get("text", "")).strip()
                except Exception:
                    pass
            likes = list(prefs_grouped.get("likes", []))
            dislikes = list(prefs_grouped.get("dislikes", []))
            topics = list(prefs_grouped.get("topics", []))
            return {
                "name": (rec.get("display_name") if rec else None) or name,
                "is_owner": bool(rec.get("is_owner", False)),
                "seen_count": int(rec.get("seen_count", 0) or 0),
                "trust_score": float(rec.get("trust_score", 0.0) or 0.0),
                "likes": likes[:5],
                "dislikes": dislikes[:5],
                "topics": topics[:6],
                "last_user_utterance": self.last_user_utterance(name),
                "top_memory": top_memory[:180],
            }
        rec = self.get(name) or {}
        prefs = rec.get("preferences", {}) if isinstance(rec.get("preferences", {}), dict) else {}
        likes = prefs.get("likes", []) if isinstance(prefs.get("likes", []), list) else []
        dislikes = prefs.get("dislikes", []) if isinstance(prefs.get("dislikes", []), list) else []
        topics = prefs.get("topics", []) if isinstance(prefs.get("topics", []), list) else []
        self._decay_moments(rec)
        moments = rec.get("moments", []) if isinstance(rec.get("moments", []), list) else []
        top_memory = ""
        if moments:
            moments.sort(key=lambda m: float(m.get("score", 0.0)), reverse=True)
            top_memory = str((moments[0] or {}).get("text", "")).strip()
        return {
            "name": rec.get("name", name),
            "is_owner": bool(rec.get("is_owner", False)),
            "seen_count": int(rec.get("seen_count", 0) or 0),
            "trust_score": float(rec.get("trust_score", 0.0) or 0.0),
            "likes": likes[:5],
            "dislikes": dislikes[:5],
            "topics": topics[:6],
            "last_user_utterance": self.last_user_utterance(name),
            "top_memory": top_memory[:180],
        }

    def get_relationship_personality_bias(self, name: str) -> Dict[str, Any]:
        """Calculates personality and tone bias depending on person familiarity and bond score."""
        prof = self.social_profile(name)
        is_owner = prof.get("is_owner", False)
        seen_count = prof.get("seen_count", 0)
        trust_score = prof.get("trust_score", 0.0)

        if is_owner:
            return {
                "status": "owner",
                "tone": "affectionate_and_warm",
                "greeting_prefix": "Efendim!",
                "trust_level": 100,
            }
        elif seen_count > 8 or trust_score > 5.0:
            return {
                "status": "friend",
                "tone": "friendly_and_playful",
                "greeting_prefix": "Tekrar merhaba!",
                "trust_level": 70,
            }
        else:
            return {
                "status": "stranger",
                "tone": "polite_and_reserved",
                "greeting_prefix": "Merhaba, sizi tanıyamadım.",
                "trust_level": 20,
            }

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
