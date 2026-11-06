from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .base import BaseSqliteRepo


class SightingsRepo(BaseSqliteRepo):
    """Append-only sighting log per person."""

    table_name = "sightings"
    ts_field = "ts"

    def record(
        self,
        person_id: str,
        *,
        ts: Optional[float] = None,
        source: str = "",
        mood: str = "",
        distance_m: Optional[float] = None,
    ) -> int:
        when = float(ts) if ts is not None else time.time()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO sightings (person_id, ts, source, mood, distance_m) VALUES (?, ?, ?, ?, ?)",
                (
                    str(person_id),
                    when,
                    str(source or ""),
                    str(mood or ""),
                    float(distance_m) if distance_m is not None else None,
                ),
            )
            return int(cur.lastrowid or 0)

    def recent_for_person(self, person_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM sightings WHERE person_id = ? ORDER BY ts DESC LIMIT ?",
            (str(person_id), max(1, int(limit))),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def purge_older_than(self, max_age_days: float = 7.0) -> int:
        return self.prune_older_than(days=max_age_days)
