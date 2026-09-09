"""In-process durable companion goal snapshots across life-loop ticks."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from .schemas import GoalSnapshot, GoalStatus

_ACTIVE_STATUSES = {GoalStatus.ACTIVE, GoalStatus.WAITING, GoalStatus.REPLANNING}
_TERMINAL_STATUSES = {
    GoalStatus.COMPLETED,
    GoalStatus.FAILED,
    GoalStatus.CANCELLED,
    GoalStatus.EXPIRED,
    GoalStatus.SUPERSEDED,
}


class GoalStore:
    """Minimal in-process goal lifecycle store. Backend-swappable later."""

    def __init__(
        self,
        *,
        ttl_s: float = 600.0,
        enabled: bool = True,
        max_terminal_keep: int = 12,
        terminal_max_age_s: float = 3600.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.ttl_s = max(1.0, float(ttl_s))
        self.max_terminal_keep = max(1, int(max_terminal_keep))
        self.terminal_max_age_s = max(60.0, float(terminal_max_age_s))
        self._items: Dict[str, GoalSnapshot] = {}

    def create(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        if not self.enabled:
            return snapshot
        now = time.time()
        snapshot.created_at = float(snapshot.created_at or now)
        snapshot.updated_at = now
        if snapshot.expires_at is None:
            snapshot.expires_at = now + self.ttl_s
        self._items[snapshot.goal_id] = snapshot
        return snapshot

    def save(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        if not self.enabled:
            return snapshot
        snapshot.updated_at = time.time()
        if snapshot.expires_at is None and snapshot.created_at:
            snapshot.expires_at = float(snapshot.created_at) + self.ttl_s
        self._items[snapshot.goal_id] = snapshot
        return snapshot

    def get(self, goal_id: str) -> Optional[GoalSnapshot]:
        return self._items.get(str(goal_id))

    def active_or_waiting(self, *, now: Optional[float] = None) -> Optional[GoalSnapshot]:
        """Return newest non-expired ACTIVE/WAITING goal with remaining work.

        Sticky REPLANNING without executable work is healed to FAILED and ignored.
        """
        self.expire_due_goals(now=now)
        self.heal_stuck_replanning(now=now)
        candidates: List[GoalSnapshot] = []
        for snap in self._items.values():
            if snap.status not in {GoalStatus.ACTIVE, GoalStatus.WAITING}:
                # REPLANNING without work already healed; with work treat as ACTIVE-equivalent
                if snap.status == GoalStatus.REPLANNING and snap.has_executable_work():
                    pass
                else:
                    continue
            if not snap.has_executable_work():
                continue
            candidates.append(snap)
        if not candidates:
            return None
        candidates.sort(key=lambda s: float(s.updated_at or 0.0), reverse=True)
        return candidates[0]

    def heal_stuck_replanning(self, *, now: Optional[float] = None) -> List[str]:
        """REPLANNING with no remaining work must not block the foreground forever."""
        ts = float(now if now is not None else time.time())
        healed: List[str] = []
        for goal_id, snap in list(self._items.items()):
            if snap.status != GoalStatus.REPLANNING:
                continue
            if snap.has_executable_work():
                # Promote sticky mid-replan with work back to WAITING for resume.
                snap.status = GoalStatus.WAITING
                snap.updated_at = ts
                snap.metadata = dict(snap.metadata or {})
                snap.metadata["healed_from"] = "replanning_with_work"
                self._items[goal_id] = snap
                healed.append(goal_id)
                continue
            snap.status = GoalStatus.FAILED
            snap.updated_at = ts
            snap.metadata = dict(snap.metadata or {})
            snap.metadata["healed_from"] = "sticky_replanning_no_work"
            self._items[goal_id] = snap
            healed.append(goal_id)
        return healed

    def mark_status(self, goal_id: str, status: GoalStatus) -> Optional[GoalSnapshot]:
        snap = self.get(goal_id)
        if snap is None:
            return None
        snap.status = status
        snap.updated_at = time.time()
        self._items[goal_id] = snap
        if status in _TERMINAL_STATUSES:
            self.prune_terminals()
        return snap

    def cancel(self, goal_id: str, *, reason: str = "cancelled") -> Optional[GoalSnapshot]:
        snap = self.mark_status(goal_id, GoalStatus.CANCELLED)
        if snap is not None:
            snap.metadata = dict(snap.metadata or {})
            snap.metadata["cancel_reason"] = str(reason)
            self._items[goal_id] = snap
        return snap

    def expire_due_goals(self, *, now: Optional[float] = None) -> List[str]:
        ts = float(now if now is not None else time.time())
        expired_ids: List[str] = []
        for goal_id, snap in list(self._items.items()):
            if snap.status in _TERMINAL_STATUSES:
                continue
            expires = snap.expires_at
            if expires is not None and float(expires) <= ts:
                snap.status = GoalStatus.EXPIRED
                snap.updated_at = ts
                self._items[goal_id] = snap
                expired_ids.append(goal_id)
        if expired_ids:
            self.prune_terminals(now=ts)
        return expired_ids

    def complete(self, goal_id: str, status: GoalStatus = GoalStatus.COMPLETED) -> Optional[GoalSnapshot]:
        if status not in _TERMINAL_STATUSES:
            status = GoalStatus.COMPLETED
        return self.mark_status(goal_id, status)

    def prune_terminals(self, *, now: Optional[float] = None) -> int:
        """Drop old terminal snapshots; keep a bounded recent history."""
        ts = float(now if now is not None else time.time())
        terminals = [
            snap
            for snap in self._items.values()
            if snap.status in _TERMINAL_STATUSES
        ]
        removed = 0
        for snap in list(terminals):
            age = ts - float(snap.updated_at or snap.created_at or ts)
            if age > self.terminal_max_age_s:
                self._items.pop(snap.goal_id, None)
                removed += 1
                terminals = [t for t in terminals if t.goal_id != snap.goal_id]
        terminals.sort(key=lambda s: float(s.updated_at or 0.0), reverse=True)
        for snap in terminals[self.max_terminal_keep :]:
            self._items.pop(snap.goal_id, None)
            removed += 1
        return removed

    def remove(self, goal_id: str) -> bool:
        return self._items.pop(str(goal_id), None) is not None

    def clear(self) -> None:
        self._items.clear()

    def all(self) -> List[GoalSnapshot]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return True


__all__ = ["GoalStore"]
