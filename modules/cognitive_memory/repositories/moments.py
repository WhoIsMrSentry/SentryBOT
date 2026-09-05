from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class MomentsRepo:
    """Salience-weighted memory snippets per person."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def add_or_boost(
        self,
        person_id: str,
        text: str,
        salience: float,
        *,
        kind: str = "note",
    ) -> int:
        """Insert a moment or boost an existing exact-text match."""
        val = str(text or "").strip()[:220]
        if not val:
            return 0
        now = time.time()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, score FROM moments WHERE person_id = ? AND text = ?",
                (str(person_id), val),
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
                INSERT INTO moments (person_id, ts, kind, text, score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(person_id), now, str(kind or "note"), val, score, now),
            )
            return int(cur.lastrowid or 0)

    def top_for_person(self, person_id: str, limit: int = 1) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM moments WHERE person_id = ? ORDER BY score DESC, updated_at DESC LIMIT ?",
            (str(person_id), max(1, int(limit))),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_for_person(self, person_id: str, limit: int = 24) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM moments WHERE person_id = ? ORDER BY updated_at DESC LIMIT ?",
            (str(person_id), max(1, int(limit))),
        )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def decay(self, person_id: str, half_life_s: float = 216000.0) -> int:
        """Apply exponential decay and drop low-score rows. Returns deleted count."""
        now = time.time()
        decay_per_sec = 0.5 / max(1.0, float(half_life_s))
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, score, updated_at FROM moments WHERE person_id = ?",
                (str(person_id),),
            ).fetchall()
            deleted = 0
            for r in rows:
                dt = max(0.0, now - float(r["updated_at"] or now))
                score = float(r["score"] or 0.0) - dt * decay_per_sec
                score = max(0.0, min(1.0, score))
                if score < 0.08:
                    conn.execute("DELETE FROM moments WHERE id = ?", (int(r["id"]),))
                    deleted += 1
                else:
                    conn.execute(
                        "UPDATE moments SET score = ?, updated_at = ? WHERE id = ?",
                        (score, now, int(r["id"])),
                    )
            return deleted

    def delete_for_person(self, person_id: str) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM moments WHERE person_id = ?", (str(person_id),)
            )
            return int(cur.rowcount or 0)

    def replace_moments_for_person(
        self,
        person_id: str,
        items: List[Dict[str, Any]],
    ) -> int:
        """Bulk replace operation used by migration to seed initial data."""
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM moments WHERE person_id = ?", (str(person_id),))
            inserted = 0
            for item in items:
                text = str(item.get("text", "") or "").strip()
                if not text:
                    continue
                conn.execute(
                    """
                    INSERT INTO moments (person_id, ts, kind, text, score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(person_id),
                        float(item.get("created_at", now) or now),
                        str(item.get("kind", "note") or "note"),
                        text,
                        float(item.get("score", 0.1) or 0.1),
                        float(item.get("updated_at", now) or now),
                    ),
                )
                inserted += 1
            return inserted
