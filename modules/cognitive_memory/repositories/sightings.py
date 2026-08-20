from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class SightingsRepo:
    """Append-only sighting log per person."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

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

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM sightings ORDER BY ts DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def purge_older_than(self, max_age_days: float = 7.0) -> int:
        cutoff = time.time() - (max_age_days * 86400.0)
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM sightings WHERE ts < ?", (cutoff,))
            return int(cur.rowcount or 0)
