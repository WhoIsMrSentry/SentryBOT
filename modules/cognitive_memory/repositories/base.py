"""Base repository pattern for SocialDB SQLite repositories.

Eliminates repetitive SQL queries for recent listing, oldest pruning, and row mapping.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class BaseSqliteRepo:
    """Base class for SocialDB table repositories."""

    table_name: str = ""
    ts_field: str = "ts"

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch the most recent rows ordered by timestamp descending."""
        if not self.table_name:
            raise NotImplementedError("table_name must be defined on repository subclasses")
        rows = self.db.fetchall(
            f"SELECT * FROM {self.table_name} ORDER BY {self.ts_field} DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def prune_older_than(self, days: float = 14.0) -> int:
        """Prune records older than the given number of days."""
        if not self.table_name:
            raise NotImplementedError("table_name must be defined on repository subclasses")
        cutoff = time.time() - max(0.0, float(days)) * 86400.0
        with self.db.transaction() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.table_name} WHERE {self.ts_field} < ?",
                (cutoff,),
            )
            return int(cur.rowcount or 0)


__all__ = ["BaseSqliteRepo"]

