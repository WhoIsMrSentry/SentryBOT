"""Per-speaker profile store (JSON) with thread-safe atomic writes."""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger("voice.speaker_id.store")


class VoiceprintStore:
    def __init__(self, store_path: str, max_profiles: int = 16) -> None:
        self.path = Path(store_path)
        self.max_profiles = max(1, int(max_profiles))
        self._lock = threading.RLock()
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                profs = data.get("profiles")
                if isinstance(profs, dict):
                    self._profiles = {
                        k: v for k, v in profs.items()
                        if isinstance(v, dict) and isinstance(v.get("vec"), list)
                    }
        except Exception as exc:
            logger.warning("speaker store load failed: %s", exc)
            self._profiles = {}

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": self._profiles, "ts": int(time.time())}
        try:
            fd, tmp = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=str(self.path.parent))
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            Path(tmp).replace(self.path)
        except Exception as exc:
            logger.warning("speaker store save failed: %s", exc)

    def upsert(self, name: str, vec: List[float], replace: bool = False) -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("speaker name is empty")
        with self._lock:
            prev = self._profiles.get(name)
            merge = prev is not None and not replace
            if merge:
                n_old = int(prev.get("n", 1))
                old = np.asarray(prev["vec"], dtype=np.float32)
                merged = ((old * n_old) + np.asarray(vec, dtype=np.float32)) / (n_old + 1)
                norm = float(np.linalg.norm(merged)) or 1.0
                vec_new = [round(float(x), 5) for x in (merged / norm)]
            else:
                vec_new = [round(float(x), 5) for x in vec]
            if name not in self._profiles and len(self._profiles) >= self.max_profiles:
                oldest = min(self._profiles, key=lambda k: self._profiles[k].get("ts", 0))
                self._profiles.pop(oldest, None)
            self._profiles[name] = {
                "vec": vec_new,
                "n": (n_old + 1) if merge else 1,
                "ts": int(time.time()),
            }
            self._save_unlocked()
            return {"ok": True, "name": name, "samples": self._profiles[name]["n"]}

    def forget(self, name: str) -> Dict[str, Any]:
        with self._lock:
            existed = self._profiles.pop(str(name or "").strip(), None)
            if existed is not None:
                self._save_unlocked()
        return {"ok": existed is not None, "name": str(name or "")}

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {name: dict(entry) for name, entry in self._profiles.items()}

    def names(self) -> List[str]:
        return list(self.all().keys())

    def count(self) -> int:
        return len(self.all())
