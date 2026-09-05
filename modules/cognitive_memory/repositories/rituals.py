from __future__ import annotations

import datetime as _dt
import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class RitualsRepo:
    """Per-day ritual bookkeeping (e.g. morning greeting, owner return)."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    @staticmethod
    def today(now: Optional[float] = None) -> str:
        ts = float(now) if now is not None else time.time()
        return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    def mark_done(self, kind: str, *, day: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        d = str(day or self.today())
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO rituals (day, kind, done_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(day, kind) DO UPDATE SET
                    done_at=excluded.done_at,
                    payload_json=excluded.payload_json
                """,
                (d, str(kind), now, json.dumps(payload or {}, ensure_ascii=True)),
            )

    def is_done(self, kind: str, *, day: Optional[str] = None) -> bool:
        d = str(day or self.today())
        row = self.db.fetchone(
            "SELECT 1 FROM rituals WHERE day = ? AND kind = ?",
            (d, str(kind)),
        )
        return row is not None

    def get(self, kind: str, *, day: Optional[str] = None) -> Optional[Dict[str, Any]]:
        d = str(day or self.today())
        row = self.db.fetchone(
            "SELECT * FROM rituals WHERE day = ? AND kind = ?",
            (d, str(kind)),
        )
        if not row:
            return None
        out = {k: row[k] for k in row.keys()}
        try:
            out["payload"] = json.loads(out.pop("payload_json") or "{}")
        except Exception:
            out["payload"] = {}
            out.pop("payload_json", None)
        return out

    def list_for_day(self, day: Optional[str] = None) -> List[Dict[str, Any]]:
        d = str(day or self.today())
        rows = self.db.fetchall(
            "SELECT day, kind, done_at FROM rituals WHERE day = ? ORDER BY done_at DESC",
            (d,),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def prune_older_than(self, days: int = 14) -> int:
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=max(0, int(days)))).strftime("%Y-%m-%d")
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM rituals WHERE day < ?", (cutoff,))
            return int(cur.rowcount or 0)
