from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class WorldMemoryRepo:
    """Persistent episodic facts, semantic entities and world events."""

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
    ) -> Dict[str, Any]:
        mid = str(memory_id).strip()
        if not mid:
            raise ValueError("memory_id cannot be empty")
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
                        location = ?, tags_json = ?
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
                        mid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO world_memories (
                        id, kind, name, summary, details_json, source,
                        confidence, salience, observation_count, first_seen, last_seen,
                        location, tags_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        mid,
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

        return self.get(mid) or {}

    def record_observation(
        self,
        memory_id: str,
        text: str,
        *,
        source: str = "autonomy",
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        mid = str(memory_id).strip()
        val = str(text or "").strip()
        if not val or not mid:
            return 0
        now = time.time()
        details_json = json.dumps(details or {}, ensure_ascii=False)
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO world_observations (ts, memory_id, source, text, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, mid, str(source), val, details_json),
            )
            return int(cur.lastrowid or 0)

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone("SELECT * FROM world_memories WHERE id = ?", (str(memory_id),))
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

    def list_by_kind(self, kind: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM world_memories WHERE kind = ? ORDER BY last_seen DESC LIMIT ?",
            (str(kind), max(1, int(limit))),
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

    def search(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        q = str(query or "").strip().lower()
        if not q:
            return []
        pattern = f"%{q}%"
        rows = self.db.fetchall(
            """
            SELECT * FROM world_memories
            WHERE name LIKE ? OR summary LIKE ? OR tags_json LIKE ?
            ORDER BY confidence DESC, last_seen DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, max(1, int(limit))),
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

    def clear(self) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM world_observations")
            conn.execute("DELETE FROM world_memories")
