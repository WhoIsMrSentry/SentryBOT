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


class ChatEpisodesRepo:
    """Per-person + per-persona chat history. Capped via :meth:`prune_for_person`."""

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
        persona_id: Optional[str] = None,
    ) -> int:
        when = float(ts) if ts is not None else time.time()
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO chat_episodes (person_id, persona_id, ts, role, text, language, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(person_id),
                    pid_scope,
                    when,
                    str(role or "user"),
                    str(text or ""),
                    str(language or ""),
                    str(summary or ""),
                ),
            )
            return int(cur.lastrowid or 0)

    def recent_for_person(
        self,
        person_id: str,
        limit: int = 16,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT * FROM chat_episodes WHERE person_id = ? AND persona_id = ? ORDER BY ts DESC, id DESC LIMIT ?",
            (str(person_id), pid_scope, max(1, int(limit))),
        )
        items = [{k: r[k] for k in r.keys()} for r in rows]
        items.reverse()
        return items

    def last_user_utterance(self, person_id: str, *, persona_id: Optional[str] = None) -> str:
        pid_scope = _scope_persona(persona_id)
        row = self.db.fetchone(
            """
            SELECT text FROM chat_episodes
            WHERE person_id = ? AND persona_id = ? AND lower(role) = 'user'
            ORDER BY ts DESC, id DESC LIMIT 1
            """,
            (str(person_id), pid_scope),
        )
        return str(row["text"]) if row else ""

    def prune_for_person(
        self,
        person_id: str,
        keep_last: int = 16,
        *,
        persona_id: Optional[str] = None,
    ) -> int:
        pid_scope = _scope_persona(persona_id)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                DELETE FROM chat_episodes
                WHERE person_id = ? AND persona_id = ?
                  AND id NOT IN (
                    SELECT id FROM chat_episodes
                    WHERE person_id = ? AND persona_id = ?
                    ORDER BY ts DESC, id DESC LIMIT ?
                  )
                """,
                (str(person_id), pid_scope, str(person_id), pid_scope, max(1, int(keep_last))),
            )
            return int(cur.rowcount or 0)
