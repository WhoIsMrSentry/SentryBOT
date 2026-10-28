from __future__ import annotations

import hashlib
import logging
import math
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("cognitive_memory.chat_rag")

_TOKEN_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)
_TR_DEVOICE = str.maketrans({"ğ": "k", "d": "t", "b": "p", "c": "ç"})

EmbedFn = Callable[[str], Any]


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(str(text or "")) if len(t) > 1]


def _stem_tokens(text: str) -> set[str]:
    words = _tokens(text)
    out = set(words)
    for w in words:
        if len(w) >= 4:
            out.add(f"#{w[:4]}")
        if len(w) >= 5:
            p5 = w[:5]
            out.add(f"#{p5[:-1] + p5[-1].translate(_TR_DEVOICE)}")
    return out


class ChatRAG:
    """Semantic long-term chat memory store (SQLite + optional embedding provider).

    Stores chat chunks that outlive the 16-episode per-person window in
    SocialDB chat_episodes, then recalls them with FTS5 keyword ranking plus an
    optional embedding-based semantic rerank. Runs on Raspberry Pi without any
    external vector database.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "db_path": "data/chat_rag.sqlite3",
        "max_per_person": 2000,
        "recall_limit": 6,
        "default_confidence": 0.5,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        self.cfg = dict(self.DEFAULTS)
        self.cfg.update(cfg)
        self.enabled = bool(self.cfg.get("enabled", True))
        self.path = Path(str(self.cfg.get("db_path") or self.DEFAULTS["db_path"]))
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fts_available = False
        self._embed_fn: Optional[EmbedFn] = None
        self._lock = threading.Lock()
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
                CREATE TABLE IF NOT EXISTS chat_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_key TEXT UNIQUE,
                    person_id TEXT NOT NULL DEFAULT '',
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'chat',
                    embedding BLOB,
                    embed_state INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_person_ts "
                "ON chat_chunks(person_id, ts DESC)"
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id TEXT NOT NULL DEFAULT '',
                    day TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ts REAL NOT NULL
                )
                """
            )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_day "
                "ON chat_summaries(person_id, day)"
            )
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chat_fts USING "
                    "fts5(id UNINDEXED, role, text, kind)"
                )
                self._fts_available = True
            except sqlite3.OperationalError:
                self._fts_available = False
            con.commit()

    def set_embedding_provider(self, fn: Optional[EmbedFn]) -> None:
        self._embed_fn = fn

    @staticmethod
    def _episode_key(person_id: str, role: str, text: str, ts: float) -> str:
        raw = f"{person_id}|{role}|{text}|{ts:.3f}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def ingest(
        self,
        *,
        person_id: Any,
        role: str,
        text: str,
        ts: Optional[float] = None,
        kind: str = "chat",
    ) -> bool:
        if not self.enabled:
            return False
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        pid = str(person_id or "")
        t = float(ts if ts is not None else time.time())
        key = self._episode_key(pid, str(role or ""), cleaned[:400], t)
        embedding = None
        embed_state = 0
        try:
            if self._embed_fn is not None:
                embedding = self._embed_fn(f"passage: {cleaned}")
                if embedding is not None:
                    import numpy as np

                    embedding = np.asarray(embedding, dtype="float32").tobytes()
                    embed_state = 1
        except Exception:
            embedding = None
            embed_state = 0
        try:
            with closing(self._connect()) as con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO chat_chunks
                        (episode_key, person_id, ts, role, text, kind, embedding, embed_state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (key, pid, t, str(role or ""), cleaned[:600], kind, embedding, embed_state),
                )
                if self._fts_available:
                    cur = con.execute(
                        "SELECT id, role, text, kind FROM chat_chunks WHERE episode_key=?",
                        (key,),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        con.execute(
                            "DELETE FROM chat_fts WHERE id=?",
                            (int(row["id"]),),
                        )
                        con.execute(
                            "INSERT INTO chat_fts(id, role, text, kind) VALUES (?, ?, ?, ?)",
                            (int(row["id"]), str(row["role"]), str(row["text"]), str(row["kind"])),
                        )
                con.commit()
            return True
        except Exception as exc:
            logger.debug("chat_rag ingest failed: %s", exc)
            return False

    def remember_day_summary(self, *, person_id: Any, day: str, text: str) -> bool:
        if not self.enabled or not str(text or "").strip():
            return False
        try:
            with closing(self._connect()) as con:
                con.execute(
                    """
                    INSERT INTO chat_summaries (person_id, day, text, ts)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(person_id, day) DO UPDATE SET text=excluded.text, ts=excluded.ts
                    """,
                    (str(person_id or ""), str(day), str(text)[:2000], time.time()),
                )
                con.commit()
            return True
        except Exception as exc:
            logger.debug("chat_rag summary save failed: %s", exc)
            return False

    def day_summaries(self, *, person_id: Any, limit: int = 7) -> List[Dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT day, text, ts FROM chat_summaries WHERE person_id=? "
                "ORDER BY day DESC LIMIT ?",
                (str(person_id or ""), max(1, min(60, int(limit)))),
            ).fetchall()
        return [
            {"day": str(row["day"]), "text": str(row["text"]), "ts": float(row["ts"])}
            for row in rows
        ]

    def recall(
        self,
        query: str,
        *,
        person_id: Any = "",
        limit: Optional[int] = None,
        kinds: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        q = str(query or "").strip()
        k = max(1, min(30, int(limit or self.cfg.get("recall_limit", 6))))
        q_tokens = set(_tokens(q))
        kind_set = {str(x).strip().lower() for x in (kinds or []) if str(x).strip()}
        rows: List[sqlite3.Row] = []
        with closing(self._connect()) as con:
            if q and self._fts_available and q_tokens:
                try:
                    fts_query = " OR ".join(f'"{t}"' for t in sorted(q_tokens))
                    sql = """
                        SELECT c.* FROM chat_fts f JOIN chat_chunks c ON c.id=f.id
                        WHERE chat_fts MATCH ?
                        ORDER BY bm25(chat_fts), c.ts DESC
                        LIMIT 200
                    """
                    if person_id:
                        sql = sql.replace("LIMIT 200", "LIMIT 200")
                    rows = con.execute(sql, (fts_query,)).fetchall()
                except Exception:
                    rows = []
            # Merge recent/embedded chunks so semantic reranking works even with zero keyword overlap
            if not rows or self._embed_fn is not None:
                if person_id:
                    extra_rows = con.execute(
                        "SELECT * FROM chat_chunks WHERE person_id=? ORDER BY ts DESC LIMIT 200",
                        (str(person_id),),
                    ).fetchall()
                else:
                    extra_rows = con.execute(
                        "SELECT * FROM chat_chunks ORDER BY ts DESC LIMIT 200"
                    ).fetchall()
                seen_ids = {int(r["id"]) for r in rows}
                for r in extra_rows:
                    if int(r["id"]) not in seen_ids:
                        rows.append(r)
                        seen_ids.add(int(r["id"]))

        now = time.time()
        q_stems = _stem_tokens(q)
        scored = []
        for row in rows:
            if person_id and str(row["person_id"] or "") != str(person_id):
                continue
            if kind_set and str(row["kind"] or "").lower() not in kind_set:
                continue
            chunk_tokens = _stem_tokens(str(row["text"])) | _stem_tokens(str(row["role"]))
            overlap = len(q_stems & chunk_tokens) / max(1, len(q_stems)) if q_stems else 0.0
            age_hours = max(0.0, (now - float(row["ts"] or now)) / 3600.0)
            recency = 1.0 / (1.0 + math.log1p(age_hours))
            score = 0.65 * overlap + 0.35 * recency
            typed: Dict[str, Any] = {
                "id": int(row["id"]),
                "ts": float(row["ts"]),
                "person_id": str(row["person_id"] or ""),
                "role": str(row["role"] or ""),
                "kind": str(row["kind"] or ""),
                "text": str(row["text"] or ""),
                "embed_state": int(row["embed_state"] or 0),
                "score": round(max(0.0, min(1.0, score)), 4),
            }
            scored.append(typed)

        semantic = self._semantic_rerank(q, scored, person_id)
        if semantic is not None:
            for item in scored:
                item["semantic"] = round(float(semantic.get(item["id"], 0.0)), 4)
                item["score"] = round(
                    max(0.0, min(1.0, 0.35 * item["score"] + 0.65 * max(0.0, item["semantic"]))),
                    4,
                )
        scored.sort(key=lambda x: (x["score"], x["ts"]), reverse=True)
        return scored[:k]

    def _semantic_rerank(
        self, query: str, scored: List[Dict[str, Any]], person_id: Any
    ) -> Optional[Dict[int, float]]:
        if self._embed_fn is None or not scored or not str(query or "").strip():
            return None
        try:
            import numpy as np

            q_vec = np.asarray(self._embed_fn(f"query: {query}"), dtype="float32")
            ids: List[int] = []
            vecs: List[Any] = []
            with closing(self._connect()) as con:
                placeholders = ",".join(["?"] * len(scored))
                rows = con.execute(
                    f"SELECT id, embedding FROM chat_chunks WHERE id IN ({placeholders})",
                    [item["id"] for item in scored],
                ).fetchall()
            for row in rows:
                blob = row["embedding"]
                if not blob:
                    continue
                vec = np.frombuffer(blob, dtype="float32")
                vecs.append(vec / max(1e-9, float(np.linalg.norm(vec))))
                ids.append(int(row["id"]))
            if not vecs:
                return None
            sim = np.asarray(vecs, dtype="float32") @ q_vec
            out_scores: Dict[int, float] = {}
            for i, raw_s in zip(ids, sim):
                s = float(raw_s)
                # E5 cosine similarities lie in [0.72, 0.94]; calibrate to [0.0, 1.0]
                calibrated = max(0.0, min(1.0, (s - 0.72) / 0.18)) if s > 0.65 else max(0.0, s)
                out_scores[i] = calibrated
            return out_scores
        except Exception as exc:
            logger.debug("semantic rerank failed: %s", exc)
            return None

    def build_context(self, query: str, *, person_id: Any = "", limit: Optional[int] = None) -> Dict[str, Any]:
        items = self.recall(query, person_id=person_id, limit=limit)
        lines = []
        for item in items:
            lines.append(f"- [{item['role']}] {item['text']}")
        return {
            "ok": True,
            "available": self.enabled,
            "query": str(query or ""),
            "context": "\n".join(lines),
            "items": items,
        }

    def prune(self) -> int:
        max_per_person = int(self.cfg.get("max_per_person", self.DEFAULTS["max_per_person"]))
        try:
            with closing(self._connect()) as con:
                cur = con.execute(
                    """
                    DELETE FROM chat_chunks
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id, ROW_NUMBER() OVER (
                                PARTITION BY person_id ORDER BY ts DESC
                            ) AS rn
                            FROM chat_chunks
                        ) WHERE rn > ?
                    )
                    """,
                    (max_per_person,),
                )
                con.execute("DELETE FROM chat_fts WHERE id NOT IN (SELECT id FROM chat_chunks)")
                con.commit()
                return int(cur.rowcount or 0)
        except Exception as exc:
            logger.debug("chat_rag prune failed: %s", exc)
            return 0

    def stats(self) -> Dict[str, Any]:
        with closing(self._connect()) as con:
            total = int(con.execute("SELECT COUNT(*) FROM chat_chunks").fetchone()[0])
            by_person: Dict[str, int] = {}
            for row in con.execute("SELECT person_id, COUNT(*) FROM chat_chunks GROUP BY person_id").fetchall():
                by_person[str(row[0] or "?")] = int(row[1])
            embedded = int(
                con.execute("SELECT COUNT(*) FROM chat_chunks WHERE embed_state=1").fetchone()[0]
            )
            summaries = int(con.execute("SELECT COUNT(*) FROM chat_summaries").fetchone()[0])
        return {
            "ok": True,
            "available": self.enabled,
            "db_path": str(self.path),
            "fts": self._fts_available,
            "total_chunks": total,
            "embedded_chunks": embedded,
            "summaries": summaries,
            "by_person": by_person,
        }

    def reset(self) -> int:
        try:
            with closing(self._connect()) as con:
                deleted = int(con.execute("DELETE FROM chat_chunks").rowcount or 0)
                con.execute("DELETE FROM chat_fts")
                con.commit()
            return deleted
        except Exception as exc:
            logger.debug("chat_rag reset failed: %s", exc)
            return 0


__all__ = ["ChatRAG", "get_default"]

_default_rag: Optional[ChatRAG] = None
_default_lock = threading.Lock()


def get_default(cfg: Optional[Dict[str, Any]] = None) -> ChatRAG:
    global _default_rag
    with _default_lock:
        if _default_rag is None:
            resolved = cfg
            if resolved is None:
                try:
                    from modules.cognitive_memory.config_loader import load_config as _load

                    module_cfg = _load() or {}
                    sub = module_cfg.get("chat_rag", {})
                    resolved = sub if isinstance(sub, dict) else {}
                except Exception:
                    resolved = {}
            _default_rag = ChatRAG(resolved)
            _hook_embedding_provider(_default_rag)
        return _default_rag


def _hook_embedding_provider(rag: ChatRAG) -> None:
    try:
        from modules.agent_core.services.system1_embed import System1EmbedEngine

        engine = System1EmbedEngine.get_instance()
        if engine.enabled:
            rag.set_embedding_provider(engine.embed_vector)
            logger.info("chat_rag semantic rerank hooked (shared System1EmbedEngine singleton)")
    except Exception:
        pass
