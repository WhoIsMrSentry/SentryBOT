from __future__ import annotations
from typing import Dict, Any, List
import threading


class StateStore:
    def __init__(self, defaults: Dict[str, Any] | None = None) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = defaults.copy() if defaults else {"operational": "idle", "emotions": []}

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._state}

    def set_operational(self, val: str) -> None:
        with self._lock:
            self._state["operational"] = val

    def set_emotions(self, vals: List[str]) -> None:
        with self._lock:
            self._state["emotions"] = list(vals)
