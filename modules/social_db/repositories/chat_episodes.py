from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class ChatEpisodesRepo:
    """Per-person chat history. Capped via :meth:`prune_for_person`."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def append(
        self,
        person_id: str,
        *,
        role: str,
        text: str,
        ts: Optional[float] = None,
        language: str = "",
        summary: str = "",
    ) -> int:
        when = float(ts) if ts is not None else time.time()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO chat_episodes (person_id, ts, role, text, language, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(person_id),
                    when,
                    str(role or "user"),
                    str(text or ""),
                    str(language or ""),
                    str(summary or ""),
                ),
            )
            return int(cur.lastrowid or 0)

    def recent_for_person(self, person_id: str, limit: int = 16) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM chat_episodes WHERE person_id = ? ORDER BY ts DESC LIMIT ?",
            (str(person_id), max(1, int(limit))),
        )
        items = [{k: r[k] for k in r.keys()} for r in rows]
        items.reverse()
        return items

    def last_user_utterance(self, person_id: str) -> str:
        row = self.db.fetchone(
            """
            SELECT text FROM chat_episodes
            WHERE person_id = ? AND lower(role) = 'user'
            ORDER BY ts DESC LIMIT 1
            """,
            (str(person_id),),
        )
        return str(row["text"]) if row else ""

    def prune_for_person(self, person_id: str, keep_last: int = 16) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                DELETE FROM chat_episodes
                WHERE person_id = ?
                  AND id NOT IN (
                    SELECT id FROM chat_episodes
                    WHERE person_id = ?
                    ORDER BY ts DESC LIMIT ?
                  )
                """,
                (str(person_id), str(person_id), max(1, int(keep_last))),
            )
            return int(cur.rowcount or 0)
