from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .base import BaseSqliteRepo


class MoodSnapshotsRepo(BaseSqliteRepo):
    """Periodic snapshots of the MoodManager state."""

    table_name = "mood_snapshots"
    ts_field = "ts"

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
