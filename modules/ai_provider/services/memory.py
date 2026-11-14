from __future__ import annotations

from collections import deque
import threading
from typing import Deque, Dict, List


class ChatMemory:
    """Thread-safe bounded rolling chat history buffer."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self.history: Deque[Dict[str, str]] = deque()
        self._lock = threading.RLock()

    def add_user(self, text: str) -> None:
        with self._lock:
            self.history.append({"role": "user", "content": text})
            self._trim_unlocked()

    def add_assistant(self, text: str) -> None:
        with self._lock:
            self.history.append({"role": "assistant", "content": text})
            self._trim_unlocked()

    def _trim_unlocked(self) -> None:
        while len(self.history) > self.max_turns:
            self.history.popleft()

    def _trim(self) -> None:
        with self._lock:
            self._trim_unlocked()

    def as_list(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self.history)
