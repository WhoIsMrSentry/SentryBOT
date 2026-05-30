from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class RelationshipMemory:
    """Lightweight per-person social memory for companion behavior.

    Backwards-compatible: when a :class:`modules.social_db.SocialDB` instance is
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
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
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
            "likes": likes[:5],
            "dislikes": dislikes[:5],
            "topics": topics[:6],
            "last_user_utterance": self.last_user_utterance(name),
            "top_memory": top_memory[:180],
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

    @staticmethod
    def _normalize(name: str) -> str:
        return str(name or "").strip().lower()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._people = raw
        except Exception:
            self._people = {}

    def _persist(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._people, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _extract_preferences_db(self, person_id: str, text: str) -> None:
        """SQLite-backed counterpart of :meth:`_extract_preferences`.

        Appends discovered likes/dislikes/topics into the ``relationships``
        table (comma-separated lists) and inserts memorable moments.
        """
        if not person_id:
            return
        low = str(text or "").strip().lower()
        if not low:
            return

        patterns_like = [
            r"\b(?:seviyorum|hoslaniyorum|bayiliyorum)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:i like|i love)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:favorim|favorite)\s+([a-z0-9_\-\s]{2,40})",
        ]
        patterns_dislike = [
            r"\b(?:sevmiyorum|nefret ediyorum)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:i hate|i dislike)\s+([a-z0-9_\-\s]{2,40})",
        ]

        existing = self._social_db.relationships.list_grouped(person_id)
        likes = existing.get("likes", [])
        dislikes = existing.get("dislikes", [])
        topics = existing.get("topics", [])
        changed = {"likes": False, "dislikes": False, "topics": False}

        for pat in patterns_like:
            for m in re.findall(pat, low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in likes:
                    likes.append(val)
                    changed["likes"] = True
                    self._social_db.moments.add_or_boost(
                        person_id=person_id, text=f"likes:{val}", salience=0.6
                    )

        for pat in patterns_dislike:
            for m in re.findall(pat, low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in dislikes:
                    dislikes.append(val)
                    changed["dislikes"] = True
                    self._social_db.moments.add_or_boost(
                        person_id=person_id, text=f"dislikes:{val}", salience=0.65
                    )

        if "?" in low:
            for token in ["muzik", "film", "oyun", "okul", "is", "hava", "spor", "robot", "yazilim", "ai"]:
                if token in low and token not in topics:
                    topics.append(token)
                    changed["topics"] = True
                    self._social_db.moments.add_or_boost(
                        person_id=person_id, text=f"topic:{token}", salience=0.45
                    )

        if changed["likes"]:
            self._social_db.relationships.set(person_id, "likes", ",".join(likes[-12:]))
        if changed["dislikes"]:
            self._social_db.relationships.set(person_id, "dislikes", ",".join(dislikes[-12:]))
        if changed["topics"]:
            self._social_db.relationships.set(person_id, "topics", ",".join(topics[-16:]))

    def _extract_preferences(self, rec: Dict[str, Any], text: str) -> None:
        prefs = rec.setdefault("preferences", {})
        likes = prefs.setdefault("likes", [])
        dislikes = prefs.setdefault("dislikes", [])
        topics = prefs.setdefault("topics", [])
        low = str(text or "").strip().lower()
        if not low:
            return

        patterns_like = [
            r"\b(?:seviyorum|hoslaniyorum|bayiliyorum)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:i like|i love)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:favorim|favorite)\s+([a-z0-9_\-\s]{2,40})",
        ]
        patterns_dislike = [
            r"\b(?:sevmiyorum|nefret ediyorum)\s+([a-z0-9_\-\s]{2,40})",
            r"\b(?:i hate|i dislike)\s+([a-z0-9_\-\s]{2,40})",
        ]

        for pat in patterns_like:
            for m in re.findall(pat, low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in likes:
                    likes.append(val)
                    self._add_moment(rec, text=f"likes:{val}", salience=0.6)

        for pat in patterns_dislike:
            for m in re.findall(pat, low):
                val = str(m).strip(" .,!?:;")
                if 2 <= len(val) <= 40 and val not in dislikes:
                    dislikes.append(val)
                    self._add_moment(rec, text=f"dislikes:{val}", salience=0.65)

        if "?" in low:
            for token in ["muzik", "film", "oyun", "okul", "is", "hava", "spor", "robot", "yazilim", "ai"]:
                if token in low and token not in topics:
                    topics.append(token)
                    self._add_moment(rec, text=f"topic:{token}", salience=0.45)

        if len(likes) > 12:
            del likes[:-12]
        if len(dislikes) > 12:
            del dislikes[:-12]
        if len(topics) > 16:
            del topics[:-16]

    def _add_moment(self, rec: Dict[str, Any], text: str, salience: float) -> None:
        moments = rec.setdefault("moments", [])
        if not isinstance(moments, list):
            rec["moments"] = []
            moments = rec["moments"]
        now = time.time()
        val = str(text or "").strip()[:220]
        if not val:
            return
        for m in moments:
            if not isinstance(m, dict):
                continue
            if str(m.get("text", "")).strip() == val:
                m["score"] = min(1.0, float(m.get("score", 0.0)) + float(salience))
                m["updated_at"] = now
                self._decay_moments(rec)
                return
        moments.append(
            {
                "text": val,
                "score": max(0.05, min(1.0, float(salience))),
                "created_at": now,
                "updated_at": now,
            }
        )
        self._decay_moments(rec)

    def _decay_moments(self, rec: Dict[str, Any]) -> None:
        moments = rec.get("moments", [])
        if not isinstance(moments, list):
            return
        now = time.time()
        half_life_s = 2.5 * 24 * 3600.0
        decay_per_sec = 0.5 / half_life_s
        kept = []
        for m in moments:
            if not isinstance(m, dict):
                continue
            updated = float(m.get("updated_at", now) or now)
            dt = max(0.0, now - updated)
            score = float(m.get("score", 0.0)) - (dt * decay_per_sec)
            score = max(0.0, min(1.0, score))
            if score < 0.08:
                continue
            m["score"] = score
            m["updated_at"] = now
            kept.append(m)
        kept.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        rec["moments"] = kept[:24]
