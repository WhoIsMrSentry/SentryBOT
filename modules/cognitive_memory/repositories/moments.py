from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from modules.common.persona_scope import get_active_persona, normalize_persona_id

from ..utils import decay_salience

if TYPE_CHECKING:
    from ..db import SocialDB


def _scope_persona(persona_id: Optional[str]) -> str:
    if persona_id is not None and str(persona_id).strip():
        return normalize_persona_id(persona_id)
    return get_active_persona()


class MomentsRepo:
    """Salience-weighted memory snippets per person and persona."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def add_or_boost(
        self,
        person_id: str,
        text: str,
        salience: float,
        *,
        kind: str = "note",
        persona_id: Optional[str] = None,
    ) -> int:
        """Insert a moment or boost an existing exact-text match."""
        val = str(text or "").strip()[:220]
        if not val:
            return 0
        now = time.time()
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, score FROM moments WHERE person_id = ? AND persona_id = ? AND text = ?",
                (str(person_id), pid_scope, val),
            ).fetchone()
            if row is not None:
                new_score = min(1.0, float(row["score"] or 0.0) + float(salience))
                conn.execute(
                    "UPDATE moments SET score = ?, updated_at = ? WHERE id = ?",
                    (new_score, now, int(row["id"])),
                )
                return int(row["id"])
            score = max(0.05, min(1.0, float(salience)))
            cur = conn.execute(
                """
                INSERT INTO moments (person_id, persona_id, ts, kind, text, score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(person_id), pid_scope, now, str(kind or "note"), val, score, now),
            )
            return int(cur.lastrowid or 0)

    def top_for_person(
        self,
        person_id: str,
        limit: int = 1,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT * FROM moments WHERE person_id = ? AND persona_id = ? ORDER BY score DESC, updated_at DESC LIMIT ?",
            (str(person_id), pid_scope, max(1, int(limit))),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_for_person(
        self,
        person_id: str,
        limit: int = 24,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT * FROM moments WHERE person_id = ? AND persona_id = ? ORDER BY updated_at DESC LIMIT ?",
            (str(person_id), pid_scope, max(1, int(limit))),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def decay(
        self,
        person_id: str,
        half_life_s: float = 216000.0,
        *,
        persona_id: Optional[str] = None,
    ) -> int:
        """Apply exponential decay and drop low-score rows. Returns deleted count."""
        now = time.time()
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, score, updated_at FROM moments WHERE person_id = ? AND persona_id = ?",
                (str(person_id), pid_scope),
            ).fetchall()
            deleted = 0
            for r in rows:
                dt = max(0.0, now - float(r["updated_at"] or now))
                score = decay_salience(float(r["score"] or 0.0), dt, half_life_s)
                if score < 0.08:
                    conn.execute("DELETE FROM moments WHERE id = ?", (int(r["id"]),))
                    deleted += 1
                else:
                    conn.execute(
                        "UPDATE moments SET score = ?, updated_at = ? WHERE id = ?",
                        (score, now, int(r["id"])),
                    )
            return deleted

    def delete_for_person(self, person_id: str, *, persona_id: Optional[str] = None) -> int:
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM moments WHERE person_id = ? AND persona_id = ?",
                (str(person_id), pid_scope),
            )
            return int(cur.rowcount or 0)

    def replace_moments_for_person(
        self,
        person_id: str,
        items: List[Dict[str, Any]],
        *,
        persona_id: Optional[str] = None,
    ) -> int:
        """Bulk replace operation used by migration to seed initial data."""
        now = time.time()
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM moments WHERE person_id = ? AND persona_id = ?",
                (str(person_id), pid_scope),
            )
            inserted = 0
            for item in items:
                text = str(item.get("text", "") or "").strip()
                if not text:
                    continue
                conn.execute(
                    """
                    INSERT INTO moments (person_id, persona_id, ts, kind, text, score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(person_id),
                        pid_scope,
                        float(item.get("created_at", now) or now),
                        str(item.get("kind", "note") or "note"),
                        text,
                        float(item.get("score", 0.1) or 0.1),
                        float(item.get("updated_at", now) or now),
                    ),
                )
                inserted += 1
            return inserted
