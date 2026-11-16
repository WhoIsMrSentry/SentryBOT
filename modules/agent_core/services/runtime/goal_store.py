"""Thread-safe durable companion goal lifecycle store (memory or SQLite)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from .schemas import GoalSnapshot, GoalStatus

_ACTIVE_STATUSES = {GoalStatus.ACTIVE, GoalStatus.WAITING, GoalStatus.REPLANNING}
_TERMINAL_STATUSES = {
    GoalStatus.COMPLETED,
    GoalStatus.FAILED,
    GoalStatus.CANCELLED,
    GoalStatus.EXPIRED,
    GoalStatus.SUPERSEDED,
}

_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[4] / "data" / "goal_store.sqlite3"


class GoalStore:
    """Thread-safe goal lifecycle store supporting ``memory`` and ``sqlite`` backends."""

    def __init__(
        self,
        *,
        ttl_s: float = 600.0,
        enabled: bool = True,
        max_terminal_keep: int = 12,
        terminal_max_age_s: float = 3600.0,
        backend: str = "memory",
        db_path: Optional[str | Path] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.ttl_s = max(1.0, float(ttl_s))
        self.max_terminal_keep = max(1, int(max_terminal_keep))
        self.terminal_max_age_s = max(60.0, float(terminal_max_age_s))
        self.backend = str(backend or "memory").strip().lower()
        self._lock = threading.RLock()
        self._items: Dict[str, GoalSnapshot] = {}
        self._conn: Optional[sqlite3.Connection] = None
        self._db_path: Optional[Path] = None

        if self.enabled and self.backend == "sqlite":
            resolved = Path(db_path) if db_path else _DEFAULT_SQLITE_PATH
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self._db_path = resolved
            self._conn = sqlite3.connect(str(resolved), check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
            self._load_from_db()

    def _load_from_db(self) -> None:
        if self._conn is None:
            return
        rows = self._conn.execute("SELECT payload_json FROM goals").fetchall()
        for (raw_json,) in rows:
            try:
                snap = GoalSnapshot.from_dict(json.loads(raw_json))
                self._items[snap.goal_id] = snap
            except Exception:
                continue

    def _persist_item(self, snap: GoalSnapshot) -> None:
        if self._conn is None:
            return
        payload = json.dumps(snap.to_dict(), ensure_ascii=False, default=str)
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO goals (goal_id, status, updated_at, expires_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snap.goal_id,
                    snap.status.value,
                    float(snap.updated_at or time.time()),
                    float(snap.expires_at) if snap.expires_at is not None else None,
                    payload,
                ),
            )

    def _delete_item(self, goal_id: str) -> None:
        if self._conn is None:
            return
        with self._conn:
            self._conn.execute("DELETE FROM goals WHERE goal_id = ?", (str(goal_id),))

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def create(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        if not self.enabled:
            return snapshot
        with self._lock:
            now = time.time()
            snapshot.created_at = float(snapshot.created_at or now)
            snapshot.updated_at = now
            if snapshot.expires_at is None:
                snapshot.expires_at = now + self.ttl_s
            self._items[snapshot.goal_id] = snapshot
            self._persist_item(snapshot)
            return snapshot

    def save(self, snapshot: GoalSnapshot) -> GoalSnapshot:
        if not self.enabled:
            return snapshot
        with self._lock:
            snapshot.updated_at = time.time()
            if snapshot.expires_at is None and snapshot.created_at:
                snapshot.expires_at = float(snapshot.created_at) + self.ttl_s
            self._items[snapshot.goal_id] = snapshot
            self._persist_item(snapshot)
            return snapshot

    def get(self, goal_id: str) -> Optional[GoalSnapshot]:
        with self._lock:
            return self._items.get(str(goal_id))

    def active_or_waiting(self, *, now: Optional[float] = None) -> Optional[GoalSnapshot]:
        """Return newest non-expired ACTIVE/WAITING goal with remaining work.

        Sticky REPLANNING without executable work is healed to FAILED and ignored.
        """
        with self._lock:
            self.expire_due_goals(now=now)
            self.heal_stuck_replanning(now=now)
            candidates: List[GoalSnapshot] = []
            for snap in self._items.values():
                if snap.status not in {GoalStatus.ACTIVE, GoalStatus.WAITING}:
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
        with self._lock:
            ts = float(now if now is not None else time.time())
            healed: List[str] = []
            for goal_id, snap in list(self._items.items()):
                if snap.status != GoalStatus.REPLANNING:
                    continue
                if snap.has_executable_work():
                    snap.status = GoalStatus.WAITING
                    snap.updated_at = ts
                    snap.metadata = dict(snap.metadata or {})
                    snap.metadata["healed_from"] = "replanning_with_work"
                    self._items[goal_id] = snap
                    self._persist_item(snap)
                    healed.append(goal_id)
                    continue
                snap.status = GoalStatus.FAILED
                snap.updated_at = ts
                snap.metadata = dict(snap.metadata or {})
                snap.metadata["healed_from"] = "sticky_replanning_no_work"
                self._items[goal_id] = snap
                self._persist_item(snap)
                healed.append(goal_id)
            return healed

    def mark_status(self, goal_id: str, status: GoalStatus) -> Optional[GoalSnapshot]:
        with self._lock:
            snap = self._items.get(str(goal_id))
            if snap is None:
                return None
            snap.status = status
            snap.updated_at = time.time()
            self._items[goal_id] = snap
            self._persist_item(snap)
            if status in _TERMINAL_STATUSES:
                self.prune_terminals()
            return snap

    def cancel(self, goal_id: str, *, reason: str = "cancelled") -> Optional[GoalSnapshot]:
        with self._lock:
            snap = self.mark_status(goal_id, GoalStatus.CANCELLED)
            if snap is not None:
                snap.metadata = dict(snap.metadata or {})
                snap.metadata["cancel_reason"] = str(reason)
                self._items[goal_id] = snap
                self._persist_item(snap)
            return snap

    def expire_due_goals(self, *, now: Optional[float] = None) -> List[str]:
        with self._lock:
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
                    self._persist_item(snap)
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
        with self._lock:
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
                    self._delete_item(snap.goal_id)
                    removed += 1
                    terminals = [t for t in terminals if t.goal_id != snap.goal_id]
            terminals.sort(key=lambda s: float(s.updated_at or 0.0), reverse=True)
            for snap in terminals[self.max_terminal_keep :]:
                self._items.pop(snap.goal_id, None)
                self._delete_item(snap.goal_id)
                removed += 1
            return removed

    def remove(self, goal_id: str) -> bool:
        with self._lock:
            removed = self._items.pop(str(goal_id), None) is not None
            if removed:
                self._delete_item(str(goal_id))
            return removed

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            if self._conn is not None:
                with self._conn:
                    self._conn.execute("DELETE FROM goals")

    def all(self) -> List[GoalSnapshot]:
        with self._lock:
            return list(self._items.values())

    def status_summary(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Thread-safe read-only status summary for diagnostic API endpoints."""
        with self._lock:
            ts = float(now if now is not None else time.time())
            self.expire_due_goals(now=ts)
            snaps = sorted(
                self._items.values(),
                key=lambda s: float(s.updated_at or 0.0),
                reverse=True,
            )
            counts = {"active": 0, "waiting": 0, "replanning": 0, "terminal": 0}
            goals_out: List[Dict[str, Any]] = []
            active_snap = None
            for snap in snaps:
                if snap.status == GoalStatus.ACTIVE:
                    counts["active"] += 1
                elif snap.status == GoalStatus.WAITING:
                    counts["waiting"] += 1
                elif snap.status == GoalStatus.REPLANNING:
                    counts["replanning"] += 1
                else:
                    counts["terminal"] += 1
                if active_snap is None and snap.status in _ACTIVE_STATUSES:
                    active_snap = snap
                plan_meta = (snap.current_plan or {}).get("metadata") if isinstance(snap.current_plan, dict) else {}
                goals_out.append(
                    {
                        "goal_id": snap.goal_id,
                        "objective": snap.objective[:160],
                        "status": snap.status.value,
                        "updated_at": snap.updated_at,
                        "ttl_remaining_s": round(max(0.0, float(snap.expires_at) - ts), 2) if snap.expires_at else None,
                        "replan_reason": (plan_meta or {}).get("replan_reason") if isinstance(plan_meta, dict) else None,
                    }
                )
            return {
                "enabled": self.enabled,
                "backend": self.backend,
                "ttl_s": self.ttl_s,
                "total": len(snaps),
                "counts": counts,
                "active_goal": goals_out[0] if active_snap and goals_out else None,
                "goals": goals_out[:20],
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __bool__(self) -> bool:
        return True


__all__ = ["GoalStore"]
