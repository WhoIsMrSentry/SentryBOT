from __future__ import annotations
from collections import deque
from typing import Deque, Dict, List


class ChatMemory:
    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self.history: Deque[Dict[str, str]] = deque()

    def add_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self) -> None:
        while len(self.history) > self.max_turns:
            self.history.popleft()

    def as_list(self) -> List[Dict[str, str]]:
        return list(self.history)
