from __future__ import annotations

import time
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class RelationshipsRepo:
    """Key/value style relationship preferences per person (likes, dislikes, topics, ...)."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def set(self, person_id: str, key: str, value: str) -> None:
        if not key:
            return
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO relationships (person_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(person_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (str(person_id), str(key), str(value or ""), now),
            )

    def list_for_person(self, person_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT key, value, updated_at FROM relationships WHERE person_id = ? ORDER BY updated_at DESC",
            (str(person_id),),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_grouped(self, person_id: str) -> Dict[str, List[str]]:
        """Return ``{key: [value, ...]}`` for keys ending with ``[]`` (csv lists are split)."""
        rows = self.db.fetchall(
            "SELECT key, value FROM relationships WHERE person_id = ?",
            (str(person_id),),
        )
        out: Dict[str, List[str]] = {}
        for r in rows:
            key = str(r["key"])
            val = str(r["value"] or "")
            if val and "," in val:
                vals = [v.strip() for v in val.split(",") if v.strip()]
            elif val:
                vals = [val]
            else:
                vals = []
            out[key] = vals
        return out

    def delete(self, person_id: str, key: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM relationships WHERE person_id = ? AND key = ?",
                (str(person_id), str(key)),
            )
            return (cur.rowcount or 0) > 0
