from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class InteractionEventsRepo:
    """Append-only log of interaction-engine and config-audit events."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def log(
        self,
        kind: str,
        *,
        count_inc: int = 1,
        payload: Optional[Dict[str, Any]] = None,
        ts: Optional[float] = None,
    ) -> int:
        when = float(ts) if ts is not None else time.time()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO interaction_events (ts, kind, count_inc, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    when,
                    str(kind or ""),
                    int(count_inc or 1),
                    json.dumps(payload or {}, ensure_ascii=True),
                ),
            )
            return int(cur.lastrowid or 0)

    def recent(self, limit: int = 50, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        if kind:
            rows = self.db.fetchall(
                "SELECT * FROM interaction_events WHERE kind = ? ORDER BY ts DESC LIMIT ?",
                (str(kind), max(1, int(limit))),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM interaction_events ORDER BY ts DESC LIMIT ?",
                (max(1, int(limit)),),
            )
        out: List[Dict[str, Any]] = []
        for r in rows:
            row = {k: r[k] for k in r.keys()}
            try:
                row["payload"] = json.loads(row.pop("payload_json") or "{}")
            except Exception:
                row["payload"] = {}
                row.pop("payload_json", None)
            out.append(row)
        return out

    def counts(self) -> Dict[str, int]:
        rows = self.db.fetchall(
            "SELECT kind, SUM(count_inc) AS total FROM interaction_events GROUP BY kind"
        )
        return {str(r["kind"]): int(r["total"] or 0) for r in rows}

    def prune_older_than(self, days: float = 30.0) -> int:
        cutoff = time.time() - max(0.0, float(days)) * 86400.0
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM interaction_events WHERE ts < ?", (cutoff,))
            return int(cur.rowcount or 0)
