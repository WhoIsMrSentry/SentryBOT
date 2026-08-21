from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, List
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
        pubsub: Dict[str, Any] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = defaults.copy() if defaults else {"operational": "idle", "emotions": []}
        self._listeners: List[Callable[[str, Any], None]] = []
        pub = pubsub or {}
        self._pubsub_enabled = bool(pub.get("enabled", True))
        keys = pub.get("keys") if isinstance(pub.get("keys"), list) else ["operational", "emotions"]
        self._pubsub_keys = {str(k) for k in keys}

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

    def subscribe(self, listener: Callable[[str, Any], None]) -> None:
        if not callable(listener):
            return
        with self._lock:
            self._listeners.append(listener)

    def _notify(self, changes: Dict[str, Any]) -> None:
        if not self._pubsub_enabled or not changes:
            return
        with self._lock:
            listeners = list(self._listeners)
        for key, value in changes.items():
            for fn in listeners:
                try:
                    fn(key, value)
                except Exception:
                    pass

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._state}

    def update(self, patch: Dict[str, Any]) -> None:
        changes: Dict[str, Any] = {}
        with self._lock:
            for key, value in patch.items():
                name = str(key)
                self._state[name] = value
                if name in self._pubsub_keys:
                    changes[name] = value
            self._persist_locked()
        self._notify(changes)

    def set_value(self, key: str, value: Any) -> None:
        name = str(key)
        with self._lock:
            self._state[name] = value
            self._persist_locked()
        if name in self._pubsub_keys:
            self._notify({name: value})

    def set_operational(self, val: str) -> None:
        with self._lock:
            self._state["operational"] = val
            self._persist_locked()
        if "operational" in self._pubsub_keys:
            self._notify({"operational": val})

    def set_emotions(self, vals: List[str]) -> None:
        values = list(vals)
        with self._lock:
            self._state["emotions"] = values
            self._persist_locked()
        if "emotions" in self._pubsub_keys:
            self._notify({"emotions": values})
