from __future__ import annotations

VLM_PEOPLE_MEMORY_COMPATIBILITY_CONTRACT = True
VLM_PEOPLE_MEMORY_ROLE = "social_db_primary_json_backward_compatibility_store"

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class PeopleMemory:
    """Thread-safe per-person chat history and last-summary memory.

    Delegates to ``SocialDB`` when registered; otherwise persists atomically to JSON.
    """

    def __init__(
        self,
        data_dir: str = "data",
        filename: str = "people_memory.json",
        social_db: Optional[object] = None,
    ) -> None:
        self.path = os.path.join(data_dir, filename)
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = {}
        os.makedirs(data_dir, exist_ok=True)
        if social_db is False:
            social_db = None
        elif social_db is None:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        if self._social_db is None:
            self._load()

    def _load(self) -> None:
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        self.data = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    self.data = {}

    def _save(self) -> None:
        p = Path(self.path)
        tmp = p.with_name(f"{p.name}.tmp.{os.getpid()}")
        try:
            with self._lock:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, p)
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
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

    def append_chat(self, person: str, role: str, text: str) -> None:
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
        with self._lock:
            rec = self.data.setdefault(person, {"chats": [], "last_summary": None, "last_seen": None})
            rec["chats"].append({"ts": time.time(), "role": role, "text": text})
            rec["last_seen"] = time.time()
            self._save()

    def set_summary(self, person: str, summary: str) -> None:
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
        with self._lock:
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
        with self._lock:
            rec = self.data.get(person)
            return dict(rec) if isinstance(rec, dict) else rec

    def list_people(self) -> List[str]:
        if self._social_db is not None:
            try:
                return [
                    str(r.get("display_name") or r.get("canonical_name") or "")
                    for r in self._social_db.persons.list_all()
                ]
            except Exception:
                return []
        with self._lock:
            return list(self.data.keys())
