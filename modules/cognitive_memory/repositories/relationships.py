from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from modules.common.persona_scope import get_active_persona, normalize_persona_id

if TYPE_CHECKING:
    from ..db import SocialDB


def _scope_persona(persona_id: Optional[str]) -> str:
    if persona_id is not None and str(persona_id).strip():
        return normalize_persona_id(persona_id)
    return get_active_persona()


class RelationshipsRepo:
    """Key/value style relationship preferences per person and persona."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def set(self, person_id: str, key: str, value: str, *, persona_id: Optional[str] = None) -> None:
        if not key:
            return
        now = time.time()
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO relationships (person_id, persona_id, key, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(person_id, persona_id, key)
                DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (str(person_id), pid_scope, str(key), str(value or ""), now),
            )

    def list_for_person(self, person_id: str, *, persona_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT key, value, updated_at FROM relationships WHERE person_id = ? AND persona_id = ? ORDER BY updated_at DESC",
            (str(person_id), pid_scope),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_grouped(self, person_id: str, *, persona_id: Optional[str] = None) -> Dict[str, List[str]]:
        """Return ``{key: [value, ...]}`` for keys ending with ``[]`` (csv lists are split)."""
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT key, value FROM relationships WHERE person_id = ? AND persona_id = ?",
            (str(person_id), pid_scope),
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

    def delete(self, person_id: str, key: str, *, persona_id: Optional[str] = None) -> bool:
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM relationships WHERE person_id = ? AND persona_id = ? AND key = ?",
                (str(person_id), pid_scope, str(key)),
            )
            return (cur.rowcount or 0) > 0
