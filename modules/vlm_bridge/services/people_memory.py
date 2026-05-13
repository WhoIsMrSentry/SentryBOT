from __future__ import annotations
import json
import os
import time
from typing import Dict, List, Any, Optional

class PeopleMemory:
    """Per-person chat history and last-summary memory.

    Single-responsibility wrapper. When a :class:`modules.social_db.SocialDB`
    instance is registered as the process default (or supplied via constructor),
    writes go through the shared SQLite store; otherwise the legacy JSON path
    is used for backward compatibility.
    """

    def __init__(
        self,
        data_dir: str = "data",
        filename: str = "people_memory.json",
        social_db: Optional[object] = None,
    ):
        self.path = os.path.join(data_dir, filename)
        self.data: Dict[str, Any] = {}
        os.makedirs(data_dir, exist_ok=True)
        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        if self._social_db is None:
            self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _resolve_pid(self, person: str) -> Optional[str]:
        if self._social_db is None:
            return None
        try:
            rec = self._social_db.persons.upsert(name=str(person))
            return str(rec.get("id") or "") or None
        except Exception:
            return None

    def append_chat(self, person: str, role: str, text: str):
        if self._social_db is not None:
            pid = self._resolve_pid(person)
            if pid:
                try:
                    self._social_db.chat_episodes.append(
                        person_id=pid, role=str(role or "user"), text=str(text or "")
                    )
                except Exception:
                    pass
            return
        rec = self.data.setdefault(person, {"chats": [], "last_summary": None, "last_seen": None})
        rec["chats"].append({"ts": time.time(), "role": role, "text": text})
        rec["last_seen"] = time.time()
        self._save()

    def set_summary(self, person: str, summary: str):
        if self._social_db is not None:
            pid = self._resolve_pid(person)
            if pid:
                try:
                    self._social_db.moments.add_or_boost(
                        person_id=pid,
                        text=str(summary or ""),
                        salience=0.7,
                        kind="summary",
                    )
                except Exception:
                    pass
            return
        rec = self.data.setdefault(person, {"chats": [], "last_summary": None, "last_seen": None})
        rec["last_summary"] = {"ts": time.time(), "text": summary}
        self._save()

    def get_person(self, person: str) -> Optional[Dict[str, Any]]:
        if self._social_db is not None:
            pid = self._resolve_pid(person)
            if not pid:
                return None
            try:
                chats = self._social_db.chat_episodes.recent_for_person(pid, limit=64)
                summaries = self._social_db.moments.top_for_person(pid, limit=1)
                return {
                    "chats": [
                        {"ts": float(c.get("ts") or 0.0), "role": c.get("role"), "text": c.get("text")}
                        for c in chats
                    ],
                    "last_summary": (
                        {"ts": float(summaries[0].get("updated_at") or 0.0), "text": summaries[0].get("text", "")}
                        if summaries
                        else None
                    ),
                }
            except Exception:
                return None
        return self.data.get(person)

    def list_people(self) -> List[str]:
        if self._social_db is not None:
            try:
                return [str(r.get("display_name") or r.get("canonical_name") or "") for r in self._social_db.persons.list_all()]
            except Exception:
                return []
        return list(self.data.keys())
