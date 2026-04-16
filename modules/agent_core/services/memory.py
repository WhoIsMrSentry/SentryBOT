import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any
import os
import re

logger = logging.getLogger("agent.memory")

class EpisodicMemory:
    """
    Long-term memory vector store / SQL DB for SentryBOT.
    Stores events, dialogue, and robot states so the Agent can recall the past.
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Resolve relative to project root (3 levels up from this file)
            base = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(base, "..", "..", ".."))
            db_path = os.path.join(project_root, "data", "memory.db")
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._conn = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _get_conn(self):
        if self._conn:
            return self._conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_type TEXT,
                    content TEXT,
                    importance INTEGER
                )
            ''')
            conn.commit()
        finally:
            if not self._conn:
                conn.close()

    def __del__(self):
        if self._conn:
            self._conn.close()

    def remember(self, event_type: str, content: str, importance: int = 1):
        """
        Save an event to long-term memory.
        event_type: 'dialogue', 'action', 'observation', 'error'
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO episodes (timestamp, event_type, content, importance) VALUES (?, ?, ?, ?)',
                (now, event_type, content, importance)
            )
            conn.commit()
        finally:
            if not self._conn:
                conn.close()
            
    def search_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves matching memory logs. 
        In a full RAG system, this would be semantic search (FAISS/Chroma).
        For now, we use SQL LIKE matching.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT timestamp, event_type, content 
                FROM episodes 
                WHERE content LIKE ? 
                ORDER BY timestamp DESC LIMIT ?
                ''',
                (f"%{query}%", limit)
            )
            results = cursor.fetchall()

            # semantic-lite fallback when LIKE results are sparse
            if len(results) < limit:
                cursor.execute(
                    '''
                    SELECT timestamp, event_type, content, importance
                    FROM episodes
                    ORDER BY timestamp DESC
                    LIMIT 300
                    '''
                )
                semantic_rows = cursor.fetchall()
            else:
                semantic_rows = []
        finally:
            if not self._conn:
                conn.close()

        out = [{"time": r[0], "type": r[1], "content": r[2]} for r in results]
        if len(out) >= limit:
            return out[:limit]

        seen = {(x["time"], x["type"], x["content"]) for x in out}
        out.extend(self._semantic_rank(query=query, rows=semantic_rows, limit=limit, seen=seen))
        return out[:limit]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-zA-Z0-9_]+", str(text).lower()) if len(t) > 1}

    def _semantic_rank(
        self,
        query: str,
        rows: List[Any],
        limit: int,
        seen: set[tuple[str, str, str]],
    ) -> List[Dict[str, Any]]:
        q_tokens = self._tokenize(query)
        if not rows or not q_tokens:
            return []

        scored: List[tuple[float, Dict[str, Any]]] = []
        total = max(1, len(rows))
        for idx, row in enumerate(rows):
            try:
                ts, ev_type, content, importance = row
            except Exception:
                continue

            key = (str(ts), str(ev_type), str(content))
            if key in seen:
                continue

            c_tokens = self._tokenize(str(content))
            if not c_tokens:
                continue
            overlap = len(q_tokens & c_tokens)
            if overlap == 0:
                continue

            lexical = overlap / max(1, len(q_tokens | c_tokens))
            recency = (total - idx) / total
            try:
                imp = max(0.0, min(1.0, float(importance) / 10.0))
            except Exception:
                imp = 0.0

            score = (0.7 * lexical) + (0.2 * recency) + (0.1 * imp)
            scored.append(
                (
                    score,
                    {
                        "time": str(ts),
                        "type": str(ev_type),
                        "content": str(content),
                        "score": round(score, 4),
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]
