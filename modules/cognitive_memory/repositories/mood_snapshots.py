from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class MoodSnapshotsRepo:
    """Periodic snapshots of the MoodManager state."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def record(
        self,
        *,
        happiness: float,
        energy: float,
        curiosity: float,
        fear: float,
        dominant: str,
        ts: Optional[float] = None,
    ) -> None:
        when = float(ts) if ts is not None else time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mood_snapshots (ts, happiness, energy, curiosity, fear, dominant)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts) DO UPDATE SET
                    happiness=excluded.happiness,
                    energy=excluded.energy,
                    curiosity=excluded.curiosity,
                    fear=excluded.fear,
                    dominant=excluded.dominant
                """,
                (when, float(happiness), float(energy), float(curiosity), float(fear), str(dominant or "neutral")),
            )

    def latest(self) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone("SELECT * FROM mood_snapshots ORDER BY ts DESC LIMIT 1")
        return {k: row[k] for k in row.keys()} if row else None

    def recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM mood_snapshots ORDER BY ts DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def prune_older_than(self, days: float = 14.0) -> int:
        cutoff = time.time() - max(0.0, float(days)) * 86400.0
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM mood_snapshots WHERE ts < ?", (cutoff,))
            return int(cur.rowcount or 0)
