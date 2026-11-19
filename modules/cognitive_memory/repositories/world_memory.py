from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from modules.common.persona_scope import DEFAULT_PERSONA_ID, get_active_persona, normalize_persona_id

if TYPE_CHECKING:
    from ..db import SocialDB


def _scope_persona(persona_id: Optional[str]) -> str:
    if persona_id is not None and str(persona_id).strip():
        return normalize_persona_id(persona_id)
    return get_active_persona()


def _scoped_memory_id(mid: str, pid: str) -> str:
    if pid != DEFAULT_PERSONA_ID and "::" not in mid:
        return f"{pid}::{mid}"[:180]
    return mid[:180]


class WorldMemoryRepo:
    """Persistent episodic facts, semantic entities and world events (per persona)."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def upsert(
        self,
        memory_id: str,
        kind: str,
        name: str,
        summary: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        confidence: float = 0.5,
        salience: float = 0.5,
        location: str = "",
        tags: Optional[List[str]] = None,
        persona_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        raw_mid = str(memory_id).strip()
        if not raw_mid:
            raise ValueError("memory_id cannot be empty")
        pid_scope = _scope_persona(persona_id)
        mid = _scoped_memory_id(raw_mid, pid_scope)
        now = time.time()
        details_json = json.dumps(details or {}, ensure_ascii=False)
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT observation_count, first_seen, confidence, salience FROM world_memories WHERE id = ?",
                (mid,),
            ).fetchone()

            if row is not None:
                new_count = int(row["observation_count"] or 1) + 1
                new_conf = min(1.0, max(float(row["confidence"] or 0.5), float(confidence)) + 0.05)
                new_sal = max(float(row["salience"] or 0.5), float(salience))
                conn.execute(
                    """
                    UPDATE world_memories
                    SET kind = ?, name = ?, summary = ?, details_json = ?, source = ?,
                        confidence = ?, salience = ?, observation_count = ?, last_seen = ?,
                        location = ?, tags_json = ?, persona_id = ?
                    WHERE id = ?
                    """,
                    (
                        str(kind),
                        str(name),
                        str(summary),
                        details_json,
                        str(source),
                        new_conf,
                        new_sal,
                        new_count,
                        now,
                        str(location),
                        tags_json,
                        pid_scope,
                        mid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO world_memories (
                        id, persona_id, kind, name, summary, details_json, source,
                        confidence, salience, observation_count, first_seen, last_seen,
                        location, tags_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        mid,
                        pid_scope,
                        str(kind),
                        str(name),
                        str(summary),
                        details_json,
                        str(source),
                        float(confidence),
                        float(salience),
                        now,
                        now,
                        str(location),
                        tags_json,
                    ),
                )

        return self.get(mid, persona_id=pid_scope) or {}

    def record_observation(
        self,
        memory_id: str,
        text: str,
        *,
        source: str = "autonomy",
        details: Optional[Dict[str, Any]] = None,
        persona_id: Optional[str] = None,
    ) -> int:
        raw_mid = str(memory_id).strip()
        val = str(text or "").strip()
        if not val or not raw_mid:
            return 0
        pid_scope = _scope_persona(persona_id)
        mid = _scoped_memory_id(raw_mid, pid_scope)
        now = time.time()
        details_json = json.dumps(details or {}, ensure_ascii=False)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO world_observations (ts, memory_id, persona_id, source, text, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, mid, pid_scope, str(source), val, details_json),
            )
            return int(cur.lastrowid or 0)

    def get(self, memory_id: str, *, persona_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        mid = str(memory_id)
        row = self.db.fetchone(
            "SELECT * FROM world_memories WHERE id = ? AND persona_id = ?",
            (mid, pid_scope),
        )
        if row is None and pid_scope != DEFAULT_PERSONA_ID and "::" not in mid:
            row = self.db.fetchone(
                "SELECT * FROM world_memories WHERE id = ? AND persona_id = ?",
                (_scoped_memory_id(mid, pid_scope), pid_scope),
            )
        if row is None:
            return None
        rec = {k: row[k] for k in row.keys()}
        try:
            rec["details"] = json.loads(rec.pop("details_json", "{}"))
        except Exception:
            rec["details"] = {}
        try:
            rec["tags"] = json.loads(rec.pop("tags_json", "[]"))
        except Exception:
            rec["tags"] = []
        return rec

    def list_by_kind(
        self,
        kind: str,
        limit: int = 50,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        pid_scope = _scope_persona(persona_id)
        rows = self.db.fetchall(
            "SELECT * FROM world_memories WHERE kind = ? AND persona_id = ? ORDER BY last_seen DESC LIMIT ?",
            (str(kind), pid_scope, max(1, int(limit))),
        )
        results = []
        for r in rows:
            rec = {k: r[k] for k in r.keys()}
            try:
                rec["details"] = json.loads(rec.pop("details_json", "{}"))
            except Exception:
                rec["details"] = {}
            try:
                rec["tags"] = json.loads(rec.pop("tags_json", "[]"))
            except Exception:
                rec["tags"] = []
            results.append(rec)
        return results

    def search(
        self,
        query: str,
        limit: int = 8,
        *,
        persona_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q = str(query or "").strip().lower()
        if not q:
            return []
        pid_scope = _scope_persona(persona_id)
        pattern = f"%{q}%"
        rows = self.db.fetchall(
            """
            SELECT * FROM world_memories
            WHERE persona_id = ? AND (name LIKE ? OR summary LIKE ? OR tags_json LIKE ?)
            ORDER BY confidence DESC, last_seen DESC
            LIMIT ?
            """,
            (pid_scope, pattern, pattern, pattern, max(1, int(limit))),
        )
        results = []
        for r in rows:
            rec = {k: r[k] for k in r.keys()}
            try:
                rec["details"] = json.loads(rec.pop("details_json", "{}"))
            except Exception:
                rec["details"] = {}
            try:
                rec["tags"] = json.loads(rec.pop("tags_json", "[]"))
            except Exception:
                rec["tags"] = []
            results.append(rec)
        return results

    def clear(self, *, persona_id: Optional[str] = None) -> None:
        with self.db.transaction() as conn:
            if persona_id is not None and str(persona_id).strip():
                pid_scope = normalize_persona_id(persona_id)
                conn.execute("DELETE FROM world_observations WHERE persona_id = ?", (pid_scope,))
                conn.execute("DELETE FROM world_memories WHERE persona_id = ?", (pid_scope,))
            else:
                conn.execute("DELETE FROM world_observations")
                conn.execute("DELETE FROM world_memories")
