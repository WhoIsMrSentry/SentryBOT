from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.relationship_storage")


class RelationshipStorageMixin:
    """JSON persistence, preference extraction, and moment decay helpers."""

    path: Optional[Path]
    _people: Dict[str, Dict[str, Any]]
    _learner: Optional[Any]
    _social_db: Optional[Any]

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

    def _get_learner(self):
        if self._learner is not None:
            return self._learner
        try:
            from .preference_learner import PreferenceLearner
            self._learner = PreferenceLearner()
        except Exception:
            self._learner = None
        return self._learner

    def _extract_preferences_db(self, person_id: str, text: str) -> None:
        if not person_id or self._social_db is None:
            return
        learner = self._get_learner()
        if learner is None:
            return
        prefs = learner.extract_preferences(text)
        existing = self._social_db.relationships.list_grouped(person_id)
        likes = existing.get("likes", [])
        dislikes = existing.get("dislikes", [])
        topics = existing.get("topics", [])
        changed = {"likes": False, "dislikes": False, "topics": False}

        for val in prefs.get("likes", []):
            if val not in likes:
                likes.append(val)
                changed["likes"] = True
                self._social_db.moments.add_or_boost(
                    person_id=person_id, text=f"likes:{val}", salience=0.6
                )

        for val in prefs.get("dislikes", []):
            if val not in dislikes:
                dislikes.append(val)
                changed["dislikes"] = True
                self._social_db.moments.add_or_boost(
                    person_id=person_id, text=f"dislikes:{val}", salience=0.65
                )

        for token in prefs.get("topics", []):
            if token not in topics:
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
        learner = self._get_learner()
        if learner is None:
            return
        prefs = learner.extract_preferences(text)

        for val in prefs.get("likes", []):
            if val not in likes:
                likes.append(val)
                self._add_moment(rec, text=f"likes:{val}", salience=0.6)

        for val in prefs.get("dislikes", []):
            if val not in dislikes:
                dislikes.append(val)
                self._add_moment(rec, text=f"dislikes:{val}", salience=0.65)

        for token in prefs.get("topics", []):
            if token not in topics:
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
