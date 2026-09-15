"""Loop / stagnation protection for AgentRuntime."""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Sequence, Tuple


class ProgressTracker:
    """Detect repeated identical actions and zero-progress iterations."""

    def __init__(
        self,
        *,
        max_identical: int = 3,
        max_zero_progress: int = 3,
        history_size: int = 12,
    ) -> None:
        self.max_identical = max(1, int(max_identical))
        self.max_zero_progress = max(1, int(max_zero_progress))
        self._history: Deque[str] = deque(maxlen=max(4, int(history_size)))
        self._zero_progress = 0
        self._last_signature = ""

    def record(self, signature: str, *, progressed: bool) -> Optional[str]:
        sig = str(signature or "").strip()
        self._history.append(sig)
        if not progressed:
            self._zero_progress += 1
        else:
            self._zero_progress = 0

        if self._zero_progress >= self.max_zero_progress:
            return "no_progress"

        if sig and self._count_trailing(sig) >= self.max_identical:
            return "repeated_identical_action"

        self._last_signature = sig
        return None

    def _count_trailing(self, signature: str) -> int:
        count = 0
        for item in reversed(self._history):
            if item != signature:
                break
            count += 1
        return count

    def reset(self) -> None:
        self._history.clear()
        self._zero_progress = 0
        self._last_signature = ""

    def restore(self, signatures: Sequence[str], *, zero_progress: int = 0) -> None:
        """Seed history from a persisted GoalSnapshot (cross-tick continuity)."""
        self.reset()
        for item in list(signatures or [])[-self._history.maxlen :]:
            self._history.append(str(item or ""))
        self._zero_progress = max(0, int(zero_progress))
        if self._history:
            self._last_signature = self._history[-1]

    def snapshot(self) -> Tuple[int, int]:
        return (len(self._history), self._zero_progress)

    def signatures(self) -> List[str]:
        return list(self._history)
