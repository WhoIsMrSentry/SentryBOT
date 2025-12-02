from __future__ import annotations
import json
import os
import time
from typing import Dict, List, Any, Optional

class PeopleMemory:
    """Kişi bazlı sohbet geçmişi ve son özet hafızası.

    Basit JSON dosyasına yazar. DryCode: tek sorumluluk, küçük API.
    """

    def __init__(self, data_dir: str = "data", filename: str = "people_memory.json"):
        self.path = os.path.join(data_dir, filename)
        self.data: Dict[str, Any] = {}
        os.makedirs(data_dir, exist_ok=True)
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

    def append_chat(self, person: str, role: str, text: str):
        rec = self.data.setdefault(person, {"chats": [], "last_summary": None, "last_seen": None})
        rec["chats"].append({"ts": time.time(), "role": role, "text": text})
        rec["last_seen"] = time.time()
        self._save()

    def set_summary(self, person: str, summary: str):
        rec = self.data.setdefault(person, {"chats": [], "last_summary": None, "last_seen": None})
        rec["last_summary"] = {"ts": time.time(), "text": summary}
        self._save()

    def get_person(self, person: str) -> Optional[Dict[str, Any]]:
        return self.data.get(person)

    def list_people(self) -> List[str]:
        return list(self.data.keys())
