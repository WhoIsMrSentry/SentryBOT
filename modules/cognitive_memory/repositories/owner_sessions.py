from __future__ import annotations

import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import BaseSqliteRepo

if TYPE_CHECKING:
    from ..db import SocialDB


class OwnerSessionsRepo(BaseSqliteRepo):
    """Tracks owner presence windows for the owner_guard layer."""

    table_name = "owner_sessions"
    ts_field = "start_ts"

    def start(self, *, source: str = "", authority_level: int = 5, notes: str = "") -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO owner_sessions (start_ts, end_ts, source, authority_level, notes)
                VALUES (?, NULL, ?, ?, ?)
                """,
                (time.time(), str(source or ""), int(authority_level), str(notes or "")),
            )
            return int(cur.lastrowid or 0)

    def end(self, session_id: int, *, notes: str = "") -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE owner_sessions SET end_ts = ?, notes = COALESCE(NULLIF(?, ''), notes) WHERE id = ? AND end_ts IS NULL",
                (time.time(), str(notes or ""), int(session_id)),
            )
            return (cur.rowcount or 0) > 0

    def end_active(self) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE owner_sessions SET end_ts = ? WHERE end_ts IS NULL",
                (time.time(),),
            )
            return int(cur.rowcount or 0)

    def active(self) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone(
            "SELECT * FROM owner_sessions WHERE end_ts IS NULL ORDER BY start_ts DESC LIMIT 1"
        )
        return {k: row[k] for k in row.keys()} if row else None
