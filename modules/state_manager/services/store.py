from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json
import sqlite3
import threading


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


class StateStore:
    def __init__(
        self,
        defaults: Dict[str, Any] | None = None,
        persistence: Dict[str, Any] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = defaults.copy() if defaults else {"operational": "idle", "emotions": []}

        cfg = persistence or {}
        self._persist_type = str(cfg.get("type", "memory")).strip().lower()
        self._persist_path = self._resolve_path(str(cfg.get("path", "modules/state_manager/data/state.sqlite3")))
        self._sqlite_conn: sqlite3.Connection | None = None

        if self._persist_type == "sqlite":
            self._init_sqlite()
            self._load_from_sqlite()
        elif self._persist_type == "json":
            self._load_from_json()

    def __del__(self) -> None:
        if self._sqlite_conn is not None:
            try:
                self._sqlite_conn.close()
            except Exception:
                pass

    @staticmethod
    def _resolve_path(path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return (_project_root() / p).resolve()

    def _init_sqlite(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(str(self._persist_path), check_same_thread=False)
        cur = self._sqlite_conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        self._sqlite_conn.commit()

    def _load_from_sqlite(self) -> None:
        if self._sqlite_conn is None:
            return
        try:
            cur = self._sqlite_conn.cursor()
            cur.execute("SELECT key, value_json FROM state")
            rows = cur.fetchall()
            if not rows:
                self._persist_locked()
                return
            loaded: Dict[str, Any] = {}
            for key, value_json in rows:
                try:
                    loaded[str(key)] = json.loads(value_json)
                except Exception:
                    continue
            if loaded:
                self._state.update(loaded)
        except Exception:
            # Keep in-memory defaults if db is unreadable.
            pass

    def _load_from_json(self) -> None:
        if not self._persist_path.exists():
            self._persist_locked()
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._state.update(data)
        except Exception:
            pass

    def _persist_locked(self) -> None:
        if self._persist_type == "memory":
            return

        if self._persist_type == "sqlite" and self._sqlite_conn is not None:
            cur = self._sqlite_conn.cursor()
            for key, value in self._state.items():
                cur.execute(
                    "INSERT OR REPLACE INTO state(key, value_json) VALUES (?, ?)",
                    (str(key), json.dumps(value, ensure_ascii=True)),
                )
            self._sqlite_conn.commit()
            return

        if self._persist_type == "json":
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self._state, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._state}

    def update(self, patch: Dict[str, Any]) -> None:
        with self._lock:
            for key, value in patch.items():
                self._state[str(key)] = value
            self._persist_locked()

    def set_value(self, key: str, value: Any) -> None:
        with self._lock:
            self._state[str(key)] = value
            self._persist_locked()

    def set_operational(self, val: str) -> None:
        with self._lock:
            self._state["operational"] = val
            self._persist_locked()

    def set_emotions(self, vals: List[str]) -> None:
        with self._lock:
            self._state["emotions"] = list(vals)
            self._persist_locked()
