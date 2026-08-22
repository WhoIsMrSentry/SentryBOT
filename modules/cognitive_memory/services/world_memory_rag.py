from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_TOKEN_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(str(text or "")) if len(t) > 1]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _clamp(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def _clean_id_part(value: Any, default: str = "unknown") -> str:
    text = str(value or default).strip().lower()
    text = text.replace(" ", "_")
    text = re.sub(r"[^a-z0-9_\-çğıöşü]+", "_", text)
    return text.strip("_") or default


class WorldMemoryRAG:
    """Local semantic world memory and RAG store.

    The store is SQLite-only so it runs on Raspberry Pi without a separate vector
    database. It uses FTS5 when available and falls back to deterministic token
    overlap ranking when FTS5 is missing. Observations are merged by stable ids;
    repeated sightings increase confidence and observation_count instead of
    blindly creating duplicates.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "db_path": "data/world_memory.sqlite3",
        "max_context_items": 8,
        "default_confidence": 0.55,
        "observation_ttl_s": 60 * 60 * 24 * 180,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self.enabled = bool(self.cfg.get("enabled", True))
        raw_path = self.cfg.get("db_path")
        if not raw_path:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                sdb = _social_default()
                if sdb is not None and hasattr(sdb, "path"):
                    raw_path = str(sdb.path)
            except Exception:
                raw_path = None
        self.path = Path(str(raw_path or self.DEFAULTS["db_path"]))
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fts_available = False
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=10.0)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with closing(self._connect()) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'unknown',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    salience REAL NOT NULL DEFAULT 0.5,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_memories_last_seen ON memories(last_seen DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_memories_name ON memories(name)")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    memory_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_observations_ts ON observations(ts DESC)")
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id UNINDEXED, kind, name, summary, tags)"
                )
                self._fts_available = True
                self._rebuild_fts(con)
            except sqlite3.OperationalError:
                self._fts_available = False

    def _rebuild_fts(self, con: sqlite3.Connection) -> None:
        if not self._fts_available:
            return
        con.execute("DELETE FROM memories_fts")
        rows = con.execute("SELECT id, kind, name, summary, tags_json FROM memories").fetchall()
        for row in rows:
            tags = " ".join(str(x) for x in _json_loads(row["tags_json"], []))
            con.execute(
                "INSERT INTO memories_fts(id, kind, name, summary, tags) VALUES (?, ?, ?, ?, ?)",
                (row["id"], row["kind"], row["name"], row["summary"], tags),
            )

    @staticmethod
    def memory_id(kind: str, name: str) -> str:
        return f"{_clean_id_part(kind, 'fact')}:{_clean_id_part(name, 'unknown')}"[:180]

    def observe(self, payload: Optional[Dict[str, Any]], *, source: str = "api") -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "available": False, "reason": "world_memory_rag_disabled"}
        body = payload if isinstance(payload, dict) else {}
        kind = str(body.get("kind") or body.get("type") or "observation").strip().lower() or "observation"
        name = str(body.get("name") or body.get("label") or body.get("title") or kind).strip() or kind
        summary = str(body.get("summary") or body.get("text") or body.get("description") or name).strip()
        location = str(body.get("location") or body.get("place") or "").strip()
        tags = body.get("tags") if isinstance(body.get("tags"), list) else []
        tags = [str(x).strip().lower() for x in tags if str(x).strip()]
        confidence = _clamp(body.get("confidence"), float(self.cfg.get("default_confidence", 0.55)), 0.0, 1.0)
        salience = _clamp(body.get("salience"), max(confidence, 0.45), 0.0, 1.0)
        details = body.get("details") if isinstance(body.get("details"), dict) else dict(body)
        now = time.time()
        memory_id = str(body.get("id") or self.memory_id(kind, name))
        with closing(self._connect()) as con:
            old = con.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            created = old is None
            if old is None:
                con.execute(
                    """
                    INSERT INTO memories(id, kind, name, summary, details_json, source, confidence, salience,
                                         observation_count, first_seen, last_seen, location, tags_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (memory_id, kind, name, summary, _json_dumps(details), source, confidence, salience, now, now, location, _json_dumps(tags)),
                )
            else:
                old_count = int(old["observation_count"] or 1)
                merged_conf = max(float(old["confidence"] or 0.0), confidence)
                merged_salience = max(float(old["salience"] or 0.0) * 0.98, salience)
                old_tags = set(_json_loads(old["tags_json"], []))
                merged_tags = sorted(old_tags.union(tags))[:32]
                previous_summary = str(old["summary"] or "")
                final_summary = summary if len(summary) >= len(previous_summary) or confidence >= float(old["confidence"] or 0.0) else previous_summary
                old_details = _json_loads(old["details_json"], {})
                if isinstance(old_details, dict):
                    merged_details = dict(old_details)
                    merged_details.update(details)
                else:
                    merged_details = details
                con.execute(
                    """
                    UPDATE memories
                    SET summary=?, details_json=?, source=?, confidence=?, salience=?, observation_count=?,
                        last_seen=?, location=CASE WHEN ? != '' THEN ? ELSE location END, tags_json=?
                    WHERE id=?
                    """,
                    (
                        final_summary,
                        _json_dumps(merged_details),
                        source,
                        merged_conf,
                        merged_salience,
                        old_count + 1,
                        now,
                        location,
                        location,
                        _json_dumps(merged_tags),
                        memory_id,
                    ),
                )
            con.execute(
                "INSERT INTO observations(ts, memory_id, source, text, details_json) VALUES (?, ?, ?, ?, ?)",
                (now, memory_id, source, summary, _json_dumps(details)),
            )
            if self._fts_available:
                con.execute("DELETE FROM memories_fts WHERE id=?", (memory_id,))
                row = con.execute("SELECT id, kind, name, summary, tags_json FROM memories WHERE id=?", (memory_id,)).fetchone()
                if row is not None:
                    tags_text = " ".join(str(x) for x in _json_loads(row["tags_json"], []))
                    con.execute(
                        "INSERT INTO memories_fts(id, kind, name, summary, tags) VALUES (?, ?, ?, ?, ?)",
                        (row["id"], row["kind"], row["name"], row["summary"], tags_text),
                    )
            con.commit()
        return {"ok": True, "available": True, "created": created, "id": memory_id, "timestamp": now, "item": self.get(memory_id)}

    def get(self, memory_id: str) -> Dict[str, Any]:
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM memories WHERE id=?", (str(memory_id),)).fetchone()
        return self._row_to_item(row) if row is not None else {}

    def recent(self, *, kind: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        limit = max(1, min(100, int(limit or 10)))
        with closing(self._connect()) as con:
            if kind:
                rows = con.execute("SELECT * FROM memories WHERE kind=? ORDER BY last_seen DESC LIMIT ?", (str(kind), limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM memories ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        return {"ok": True, "available": True, "items": [self._row_to_item(row) for row in rows]}

    def recall(self, query: str, *, limit: int = 8, kinds: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "available": False, "reason": "world_memory_rag_disabled", "items": []}
        q = str(query or "").strip()
        limit = max(1, min(30, int(limit or self.cfg.get("max_context_items", 8))))
        q_tokens = set(_tokens(q))
        kind_set = {str(k).strip().lower() for k in kinds or [] if str(k).strip()}
        rows: List[sqlite3.Row] = []
        with closing(self._connect()) as con:
            if q and self._fts_available and q_tokens:
                try:
                    fts_query = " OR ".join(sorted(q_tokens))
                    sql = """
                        SELECT m.* FROM memories_fts f JOIN memories m ON m.id=f.id
                        WHERE memories_fts MATCH ?
                        ORDER BY bm25(memories_fts), m.salience DESC, m.last_seen DESC
                        LIMIT ?
                    """
                    rows = con.execute(sql, (fts_query, limit * 3)).fetchall()
                except Exception:
                    rows = []
            if not rows:
                rows = con.execute("SELECT * FROM memories ORDER BY salience DESC, last_seen DESC LIMIT ?", (limit * 8,)).fetchall()
        ranked = []
        now = time.time()
        for row in rows:
            item = self._row_to_item(row)
            if kind_set and item.get("kind") not in kind_set:
                continue
            text = " ".join([str(item.get("kind", "")), str(item.get("name", "")), str(item.get("summary", "")), " ".join(item.get("tags", []))])
            tks = set(_tokens(text))
            overlap = len(q_tokens & tks) / max(1, len(q_tokens)) if q_tokens else 0.0
            age_hours = max(0.0, (now - float(item.get("last_seen", now))) / 3600.0)
            recency = 1.0 / (1.0 + math.log1p(age_hours))
            score = 0.50 * overlap + 0.25 * float(item.get("salience", 0.0)) + 0.15 * float(item.get("confidence", 0.0)) + 0.10 * recency
            item["rank_score"] = round(score, 4)
            ranked.append(item)
        ranked.sort(key=lambda item: (float(item.get("rank_score", 0.0)), float(item.get("last_seen", 0.0))), reverse=True)
        return {"ok": True, "available": True, "query": q, "items": ranked[:limit]}

    def build_context(self, query: str, *, limit: int = 8) -> Dict[str, Any]:
        recalled = self.recall(query, limit=limit)
        items = recalled.get("items", []) if isinstance(recalled, dict) else []
        lines = []
        for item in items:
            lines.append(
                f"- {item.get('kind')}:{item.get('name')} | {item.get('summary')} | "
                f"confidence={item.get('confidence')} seen={item.get('observation_count')}"
            )
        return {"ok": True, "available": True, "query": str(query or ""), "context": "\n".join(lines), "items": items}

    def forget(self, memory_id: str = "", *, kind: str = "") -> Dict[str, Any]:
        with closing(self._connect()) as con:
            if memory_id:
                count = con.execute("DELETE FROM memories WHERE id=?", (memory_id,)).rowcount
                con.execute("DELETE FROM observations WHERE memory_id=?", (memory_id,))
                if self._fts_available:
                    con.execute("DELETE FROM memories_fts WHERE id=?", (memory_id,))
            elif kind:
                ids = [row[0] for row in con.execute("SELECT id FROM memories WHERE kind=?", (kind,)).fetchall()]
                count = len(ids)
                con.execute("DELETE FROM memories WHERE kind=?", (kind,))
                for mid in ids:
                    con.execute("DELETE FROM observations WHERE memory_id=?", (mid,))
                    if self._fts_available:
                        con.execute("DELETE FROM memories_fts WHERE id=?", (mid,))
            else:
                count = con.execute("DELETE FROM memories").rowcount
                con.execute("DELETE FROM observations")
                if self._fts_available:
                    con.execute("DELETE FROM memories_fts")
            con.commit()
        return {"ok": True, "available": True, "deleted": int(count or 0)}

    def prune_unimportant_memories(self, age_threshold_s: float = 86400 * 7, min_salience: float = 0.5) -> Dict[str, Any]:
        """Deletes memories that are old, low salience, and low confidence."""
        if not self.enabled:
            return {"ok": False, "deleted": 0}
        now = time.time()
        cutoff_time = now - age_threshold_s
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT id FROM memories WHERE last_seen < ? AND salience < ? AND confidence < ?",
                (cutoff_time, min_salience, min_salience)
            ).fetchall()
            ids_to_delete = [row[0] for row in rows]
            
            if not ids_to_delete:
                return {"ok": True, "deleted": 0}
                
            for mid in ids_to_delete:
                con.execute("DELETE FROM memories WHERE id=?", (mid,))
                con.execute("DELETE FROM observations WHERE memory_id=?", (mid,))
                if self._fts_available:
                    con.execute("DELETE FROM memories_fts WHERE id=?", (mid,))
            
            con.commit()
            
        return {"ok": True, "deleted": len(ids_to_delete)}

    def consolidate_memories(self) -> Dict[str, Any]:
        """Dream cycle: merge highly repetitive but slightly distinct observations, boost salience of important ones."""
        if not self.enabled:
            return {"ok": False, "consolidated": 0}
        
        # A simple form of consolidation: if an object has > 10 observations, we boost its salience
        # and delete old observations from the observations table to keep size small.
        with closing(self._connect()) as con:
            rows = con.execute("SELECT id, observation_count, salience FROM memories WHERE observation_count > 5").fetchall()
            updated = 0
            for row in rows:
                mid = row[0]
                count = row[1]
                salience = float(row[2])
                new_salience = min(1.0, salience + (count * 0.01))
                
                con.execute("UPDATE memories SET salience=? WHERE id=?", (new_salience, mid))
                # Prune old observation events for this memory
                con.execute(
                    "DELETE FROM observations WHERE memory_id=? AND id NOT IN (SELECT id FROM observations WHERE memory_id=? ORDER BY ts DESC LIMIT 5)",
                    (mid, mid)
                )
                updated += 1
                
            con.commit()
                
        return {"ok": True, "consolidated": updated}

    def status(self) -> Dict[str, Any]:
        with closing(self._connect()) as con:
            total = int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
            by_kind = {str(row[0]): int(row[1]) for row in con.execute("SELECT kind, COUNT(*) FROM memories GROUP BY kind").fetchall()}
            observations = int(con.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
        return {"ok": True, "available": True, "enabled": self.enabled, "db_path": str(self.path), "fts": self._fts_available, "total": total, "observations": observations, "by_kind": by_kind}

    def schema(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "available": True,
            "tables": ["memories", "observations", "memories_fts" if self._fts_available else "fallback_ranker"],
            "kinds": ["person", "place", "object", "episode", "preference", "fact", "observation", "sound", "decision"],
            "fields": ["id", "kind", "name", "summary", "confidence", "salience", "source", "location", "tags", "first_seen", "last_seen", "observation_count"],
        }

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "name": row["name"],
            "summary": row["summary"],
            "details": _json_loads(row["details_json"], {}),
            "source": row["source"],
            "confidence": round(float(row["confidence"] or 0.0), 3),
            "salience": round(float(row["salience"] or 0.0), 3),
            "observation_count": int(row["observation_count"] or 0),
            "first_seen": float(row["first_seen"] or 0.0),
            "last_seen": float(row["last_seen"] or 0.0),
            "location": row["location"],
            "tags": _json_loads(row["tags_json"], []),
        }


__all__ = ["WorldMemoryRAG"]
