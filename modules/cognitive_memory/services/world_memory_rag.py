from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils import backup_sqlite_connection, resolve_repo_path
from .text_utils import _stem_tokens, _tokens

logger = logging.getLogger("cognitive_memory.world_memory_rag")

EmbedFn = Callable[[str], Any]


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
    """Local semantic world memory and RAG store backed by persistent SQLite + FTS5."""

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
        self.path = resolve_repo_path(str(raw_path or self.DEFAULTS["db_path"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = self._open_conn()
        self._fts_available = False
        self._embed_fn: Optional[EmbedFn] = None
        self._init_db()
        _hook_embedding_provider(self)

    def _open_conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=10.0, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def set_embedding_provider(self, fn: Optional[EmbedFn]) -> None:
        self._embed_fn = fn

    def _init_db(self) -> None:
        with self._lock:
            con = self._conn
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
                    expiry REAL NOT NULL DEFAULT 0.0,
                    supersedes TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    embedding BLOB,
                    embed_state INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            for col_ddl in (
                "ALTER TABLE memories ADD COLUMN embedding BLOB",
                "ALTER TABLE memories ADD COLUMN expiry REAL NOT NULL DEFAULT 0.0",
                "ALTER TABLE memories ADD COLUMN supersedes TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE memories ADD COLUMN embed_state INTEGER NOT NULL DEFAULT 0",
            ):
                try:
                    con.execute(col_ddl)
                except sqlite3.OperationalError:
                    pass
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
                fts_cnt = int(con.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0])
                mem_cnt = int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
                if fts_cnt == 0 and mem_cnt > 0:
                    self._rebuild_fts(con)
            except sqlite3.OperationalError:
                self._fts_available = False
            con.commit()

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

    def _compute_embedding(self, text: str) -> tuple[Optional[bytes], int]:
        if self._embed_fn is None:
            return None, 0
        try:
            raw_vec = self._embed_fn(f"passage: {text}")
            if raw_vec is not None:
                import numpy as np

                return np.asarray(raw_vec, dtype="float32").tobytes(), 1
        except Exception:
            pass
        return None, 0

    def observe(
        self,
        payload: Optional[Dict[str, Any]],
        *,
        source: str = "api",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
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
        ts_now = float(now if now is not None else time.time())
        observed_at = _clamp(body.get("observed_at"), ts_now, 0.0, ts_now + 86400.0 * 3650)
        explicit_exp = _clamp(body.get("expiry") or body.get("expiry_ts"), 0.0, 0.0, ts_now + 86400.0 * 3650)
        ttl_s = _clamp(body.get("expiry_s"), 0.0, 0.0, 86400.0 * 3650)
        expiry = explicit_exp if explicit_exp > observed_at else (observed_at + ttl_s if ttl_s > 0.0 else 0.0)
        supersedes = str(body.get("supersedes") or "").strip()
        memory_id = str(body.get("id") or self.memory_id(kind, name))

        embedding, embed_state = self._compute_embedding(f"{kind} {name} {summary}")

        with self._lock:
            con = self._conn
            if supersedes and supersedes != memory_id:
                con.execute("DELETE FROM memories WHERE id=?", (supersedes,))
                con.execute("DELETE FROM observations WHERE memory_id=?", (supersedes,))
                if self._fts_available:
                    con.execute("DELETE FROM memories_fts WHERE id=?", (supersedes,))

            old = con.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            created = old is None
            if old is None:
                con.execute(
                    """
                    INSERT INTO memories(id, kind, name, summary, details_json, source, confidence, salience,
                                         observation_count, first_seen, last_seen, expiry, supersedes, location,
                                         tags_json, embedding, embed_state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        kind,
                        name,
                        summary,
                        _json_dumps(details),
                        source,
                        confidence,
                        salience,
                        ts_now,
                        ts_now,
                        expiry,
                        supersedes,
                        location,
                        _json_dumps(tags),
                        embedding,
                        embed_state,
                    ),
                )
            else:
                old_count = int(old["observation_count"] or 1)
                merged_conf = max(float(old["confidence"] or 0.0), confidence)
                merged_salience = max(float(old["salience"] or 0.0) * 0.98, salience)
                old_tags = set(_json_loads(old["tags_json"], []))
                merged_tags = sorted(old_tags.union(tags))[:32]
                previous_summary = str(old["summary"] or "")
                final_summary = (
                    summary
                    if len(summary) >= len(previous_summary) or confidence >= float(old["confidence"] or 0.0)
                    else previous_summary
                )
                old_details = _json_loads(old["details_json"], {})
                if isinstance(old_details, dict):
                    merged_details = dict(old_details)
                    merged_details.update(details)
                else:
                    merged_details = details
                final_embedding = embedding if embedding is not None else old["embedding"]
                final_embed_state = 1 if final_embedding is not None else int(old["embed_state"] or 0)
                con.execute(
                    """
                    UPDATE memories
                    SET summary=?, details_json=?, source=?, confidence=?, salience=?, observation_count=?,
                        last_seen=?, expiry=?, supersedes=CASE WHEN ? != '' THEN ? ELSE supersedes END,
                        location=CASE WHEN ? != '' THEN ? ELSE location END, tags_json=?, embedding=?, embed_state=?
                    WHERE id=?
                    """,
                    (
                        final_summary,
                        _json_dumps(merged_details),
                        source,
                        merged_conf,
                        merged_salience,
                        old_count + 1,
                        ts_now,
                        expiry,
                        supersedes,
                        supersedes,
                        location,
                        location,
                        _json_dumps(merged_tags),
                        final_embedding,
                        final_embed_state,
                        memory_id,
                    ),
                )
            con.execute(
                "INSERT INTO observations(ts, memory_id, source, text, details_json) VALUES (?, ?, ?, ?, ?)",
                (ts_now, memory_id, source, summary, _json_dumps(details)),
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
        return {"ok": True, "available": True, "created": created, "id": memory_id, "timestamp": ts_now, "item": self.get(memory_id, now=ts_now)}

    def get(self, memory_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts_now = float(now if now is not None else time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE id=? AND (expiry = 0 OR expiry > ?)",
                (str(memory_id), ts_now),
            ).fetchone()
        return self._row_to_item(row) if row is not None else {}

    def recent(self, *, kind: Optional[str] = None, limit: int = 10, now: Optional[float] = None) -> Dict[str, Any]:
        limit = max(1, min(100, int(limit or 10)))
        ts_now = float(now if now is not None else time.time())
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE kind=? AND (expiry = 0 OR expiry > ?) ORDER BY last_seen DESC LIMIT ?",
                    (str(kind), ts_now, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE (expiry = 0 OR expiry > ?) ORDER BY last_seen DESC LIMIT ?",
                    (ts_now, limit),
                ).fetchall()
        return {"ok": True, "available": True, "items": [self._row_to_item(row) for row in rows]}

    def recall(
        self,
        query: str,
        *,
        limit: int = 8,
        kinds: Optional[Sequence[str]] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "available": False, "reason": "world_memory_rag_disabled", "items": []}
        q = str(query or "").strip()
        limit = max(1, min(30, int(limit or self.cfg.get("max_context_items", 8))))
        q_tokens = set(_tokens(q))
        kind_list = sorted({str(k).strip().lower() for k in kinds or [] if str(k).strip()})
        ts_now = float(now if now is not None else time.time())

        kind_clause = ""
        kind_params: List[Any] = []
        if kind_list:
            placeholders = ",".join(["?"] * len(kind_list))
            kind_clause = f" AND LOWER(m.kind) IN ({placeholders})"
            kind_params = list(kind_list)

        rows: List[sqlite3.Row] = []
        with self._lock:
            con = self._conn
            if q and self._fts_available and q_tokens:
                try:
                    fts_query = " OR ".join(f'"{t.replace(chr(34), "")}"' for t in sorted(q_tokens))
                    sql = f"""
                        SELECT m.* FROM memories_fts f JOIN memories m ON m.id=f.id
                        WHERE memories_fts MATCH ? AND (m.expiry = 0 OR m.expiry > ?){kind_clause}
                        ORDER BY bm25(memories_fts), m.salience DESC, m.last_seen DESC
                        LIMIT ?
                    """
                    rows = con.execute(sql, (fts_query, ts_now, *kind_params, limit * 3)).fetchall()
                except Exception:
                    rows = []
            if not rows or self._embed_fn is not None:
                extra_kind_clause = f" AND LOWER(kind) IN ({','.join(['?'] * len(kind_list))})" if kind_list else ""
                sql_extra = f"""
                    SELECT * FROM memories
                    WHERE (expiry = 0 OR expiry > ?){extra_kind_clause}
                    ORDER BY salience DESC, last_seen DESC LIMIT ?
                """
                extra_rows = con.execute(sql_extra, (ts_now, *kind_params, limit * 8)).fetchall()
                seen_ids = {str(r["id"]) for r in rows}
                for r in extra_rows:
                    if str(r["id"]) not in seen_ids:
                        rows.append(r)
                        seen_ids.add(str(r["id"]))

        ranked = []
        q_stems = _stem_tokens(q)
        for row in rows:
            item = self._row_to_item(row)
            text = " ".join([str(item.get("kind", "")), str(item.get("name", "")), str(item.get("summary", "")), " ".join(item.get("tags", []))])
            tks = _stem_tokens(text)
            overlap = len(q_stems & tks) / max(1, len(q_stems)) if q_stems else 0.0
            age_hours = max(0.0, (ts_now - float(item.get("last_seen", ts_now))) / 3600.0)
            recency = 1.0 / (1.0 + math.log1p(age_hours))
            score = 0.50 * overlap + 0.25 * float(item.get("salience", 0.0)) + 0.15 * float(item.get("confidence", 0.0)) + 0.10 * recency
            item["rank_score"] = round(score, 4)
            ranked.append(item)
        semantic = self._semantic_rerank(q, ranked)
        if semantic is not None:
            for item in ranked:
                sem = round(float(semantic.get(str(item["id"]), 0.0)), 4)
                item["semantic"] = sem
                item["rank_score"] = round(
                    max(0.0, min(1.0, 0.40 * float(item.get("rank_score", 0.0)) + 0.60 * max(0.0, sem))),
                    4,
                )
        ranked.sort(key=lambda item: (float(item.get("rank_score", 0.0)), float(item.get("last_seen", 0.0))), reverse=True)
        return {"ok": True, "available": True, "query": q, "items": ranked[:limit]}

    def _semantic_rerank(self, query: str, ranked: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        if self._embed_fn is None or not ranked or not str(query or "").strip():
            return None
        try:
            import numpy as np

            q_vec = np.asarray(self._embed_fn(f"query: {query}"), dtype="float32")
            q_norm = max(1e-9, float(np.linalg.norm(q_vec)))
            q_vec = q_vec / q_norm
            ids: List[str] = []
            vecs: List[Any] = []
            with self._lock:
                placeholders = ",".join(["?"] * len(ranked))
                rows = self._conn.execute(
                    f"SELECT id, embedding FROM memories WHERE id IN ({placeholders})",
                    [str(item["id"]) for item in ranked],
                ).fetchall()
            for row in rows:
                blob = row["embedding"]
                if not blob:
                    continue
                vec = np.frombuffer(blob, dtype="float32")
                if vec.shape != q_vec.shape:
                    continue
                vecs.append(vec / max(1e-9, float(np.linalg.norm(vec))))
                ids.append(str(row["id"]))
            if not vecs:
                return None
            sim = np.asarray(vecs, dtype="float32") @ q_vec
            out_scores: Dict[str, float] = {}
            for mid, raw_s in zip(ids, sim):
                s = float(raw_s)
                calibrated = max(0.0, min(1.0, (s - 0.72) / 0.18)) if s > 0.65 else max(0.0, s)
                out_scores[mid] = calibrated
            return out_scores
        except Exception as exc:
            logger.debug("world_memory_rag semantic rerank failed: %s", exc)
            return None

    def backfill_embeddings(self, batch_size: int = 32) -> int:
        """Compute embeddings in background for unembedded memories (embed_state=0)."""
        if not self.enabled or self._embed_fn is None:
            return 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, name, summary FROM memories WHERE embed_state = 0 ORDER BY last_seen DESC LIMIT ?",
                (max(1, int(batch_size)),),
            ).fetchall()
        updates: List[tuple[bytes, str]] = []
        for row in rows:
            blob, ok = self._compute_embedding(f"{row['kind']} {row['name']} {row['summary']}")
            if ok and blob is not None:
                updates.append((blob, str(row["id"])))
        if not updates:
            return 0
        with self._lock:
            self._conn.executemany(
                "UPDATE memories SET embedding = ?, embed_state = 1 WHERE id = ?",
                updates,
            )
            self._conn.commit()
        return len(updates)

    def backup(self, dest_path: str | Path) -> Path:
        """Create a safe online SQLite snapshot via sqlite3.Connection.backup()."""
        return backup_sqlite_connection(self._conn, self._lock, dest_path)

    def build_context(self, query: str, *, limit: int = 8) -> Dict[str, Any]:
        recalled = self.recall(query, limit=limit)
        items = recalled.get("items", []) if isinstance(recalled, dict) else []
        lines = [
            f"- {item.get('kind')}:{item.get('name')} | {item.get('summary')} | "
            f"confidence={item.get('confidence')} seen={item.get('observation_count')}"
            for item in items
        ]
        return {"ok": True, "available": True, "query": str(query or ""), "context": "\n".join(lines), "items": items}

    def forget(self, memory_id: str = "", *, kind: str = "") -> Dict[str, Any]:
        with self._lock:
            con = self._conn
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
        """Deletes memories that are expired or old, low salience, and low confidence."""
        if not self.enabled:
            return {"ok": False, "deleted": 0}
        now = time.time()
        cutoff_time = now - age_threshold_s
        with self._lock:
            con = self._conn
            rows = con.execute(
                "SELECT id FROM memories WHERE (expiry > 0 AND expiry <= ?) OR (last_seen < ? AND salience < ? AND confidence < ?)",
                (now, cutoff_time, min_salience, min_salience),
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
        """Dream cycle: boost salience of repeatedly seen items and trim verbose observation history."""
        if not self.enabled:
            return {"ok": False, "consolidated": 0}
        with self._lock:
            con = self._conn
            rows = con.execute("SELECT id, observation_count, salience FROM memories WHERE observation_count > 5").fetchall()
            updated = 0
            for row in rows:
                mid = row[0]
                count = row[1]
                salience = float(row[2])
                new_salience = min(1.0, salience + (count * 0.01))
                con.execute("UPDATE memories SET salience=? WHERE id=?", (new_salience, mid))
                con.execute(
                    "DELETE FROM observations WHERE memory_id=? AND id NOT IN (SELECT id FROM observations WHERE memory_id=? ORDER BY ts DESC LIMIT 5)",
                    (mid, mid),
                )
                updated += 1
            con.commit()
        return {"ok": True, "consolidated": updated}

    def status(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts_now = float(now if now is not None else time.time())
        with self._lock:
            con = self._conn
            total = int(con.execute("SELECT COUNT(*) FROM memories WHERE expiry = 0 OR expiry > ?", (ts_now,)).fetchone()[0])
            by_kind = {
                str(row[0]): int(row[1])
                for row in con.execute(
                    "SELECT kind, COUNT(*) FROM memories WHERE expiry = 0 OR expiry > ? GROUP BY kind",
                    (ts_now,),
                ).fetchall()
            }
            observations = int(con.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
            unembedded = int(con.execute("SELECT COUNT(*) FROM memories WHERE embed_state = 0").fetchone()[0])
        return {
            "ok": True,
            "available": True,
            "enabled": self.enabled,
            "db_path": str(self.path),
            "fts": self._fts_available,
            "total": total,
            "unembedded": unembedded,
            "observations": observations,
            "by_kind": by_kind,
        }

    def schema(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "available": True,
            "tables": ["memories", "observations", "memories_fts" if self._fts_available else "fallback_ranker"],
            "kinds": ["person", "place", "object", "episode", "preference", "fact", "observation", "sound", "decision"],
            "fields": ["id", "kind", "name", "summary", "confidence", "salience", "source", "location", "tags", "first_seen", "last_seen", "expiry", "observation_count"],
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
            "expiry": float(row["expiry"] or 0.0),
            "supersedes": str(row["supersedes"] or ""),
            "location": row["location"],
            "tags": _json_loads(row["tags_json"], []),
        }


_default_world_rag: Optional[WorldMemoryRAG] = None
_default_world_lock = threading.Lock()


def get_default(cfg: Optional[Dict[str, Any]] = None) -> WorldMemoryRAG:
    """Return process-wide shared WorldMemoryRAG singleton."""
    global _default_world_rag
    with _default_world_lock:
        if _default_world_rag is None:
            resolved = cfg
            if resolved is None:
                try:
                    from modules.cognitive_memory.config_loader import load_config as _load

                    module_cfg = _load() or {}
                    sub = module_cfg.get("world_memory", {})
                    resolved = sub if isinstance(sub, dict) else {}
                except Exception:
                    resolved = {}
            _default_world_rag = WorldMemoryRAG(resolved)
        return _default_world_rag


def reset_default() -> None:
    """Close and clear process-wide WorldMemoryRAG singleton (for tests)."""
    global _default_world_rag
    with _default_world_lock:
        if _default_world_rag is not None:
            _default_world_rag.close()
        _default_world_rag = None


def _hook_embedding_provider(rag: WorldMemoryRAG) -> None:
    from .embedding_hook import hook_embedding_provider

    hook_embedding_provider(rag, name="world_memory_rag")


__all__ = ["WorldMemoryRAG", "get_default", "reset_default"]
