from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
import copy
import json
import logging
import os
import sqlite3
import threading

logger = logging.getLogger("state_manager.store")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


class StateStore:
    """Shared robot state with optional persistence and key pub/sub.

    Concurrency design (R41-R45): an RLock guards the in-memory dict only;
    persistence writes happen OUTSIDE that lock against a deep-copied
    snapshot, serialized by a dedicated ``_persist_lock`` so slow disk I/O or
    a busy SQLite file can never stall the 798 fan-in write paths.
    """

    def __init__(
        self,
        defaults: Dict[str, Any] | None = None,
        persistence: Dict[str, Any] | None = None,
        pubsub: Dict[str, Any] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._persist_lock = threading.Lock()
        self._state: Dict[str, Any] = defaults.copy() if defaults else {"operational": "idle", "emotions": []}
        self._listeners: List[Callable[[str, Any], None]] = []
        pub = pubsub or {}
        self._pubsub_enabled = bool(pub.get("enabled", True))
        keys = pub.get("keys") if isinstance(pub.get("keys"), list) else ["operational", "emotions"]
        self._pubsub_keys = {str(k) for k in keys}

        cfg = persistence or {}
        self._persist_type = str(cfg.get("type", "memory")).strip().lower()
        self._persist_path = self._resolve_path(str(cfg.get("path", "data/state.sqlite3")))
        self._sqlite_conn: sqlite3.Connection | None = None

        if self._persist_type == "sqlite":
            self._init_sqlite()
            self._load_from_sqlite()
        elif self._persist_type == "json":
            self._load_from_json()

    def close(self) -> None:
        """Close the SQLite persistence connection idempotently."""
        with self._persist_lock:
            conn = self._sqlite_conn
            if conn is not None:
                self._sqlite_conn = None
                try:
                    conn.close()
                except Exception as exc:
                    logger.debug("SQLite close failed: %s", exc)

    def __del__(self) -> None:
        try:
            self.close()
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
        # WAL + busy_timeout keep a second process (or a slow checkpoint) from
        # producing "database is locked" on the robot (R44).
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
        except Exception as exc:
            logger.warning("SQLite PRAGMA initialization failed: %s", exc)
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
                except Exception as exc:
                    logger.debug("Skipping corrupt state row %r: %s", key, exc)
                    continue
            if loaded:
                self._state.update(loaded)
        except Exception as exc:
            # Keep in-memory defaults if db is unreadable.
            logger.warning("Failed to load SQLite state from %s: %s", self._persist_path, exc)

    def _load_from_json(self) -> None:
        if not self._persist_path.exists():
            self._persist_locked()
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._state.update(data)
        except Exception as exc:
            logger.warning("Failed to load JSON state from %s: %s", self._persist_path, exc)

    def _snapshot_locked(self, keys: Iterable[str] | None = None) -> Dict[str, Any]:
        if keys is None:
            return copy.deepcopy(self._state)
        return {k: copy.deepcopy(self._state[k]) for k in keys if k in self._state}

    def _persist_locked(self) -> None:
        """Persist the full current state. Caller must hold ``_lock``
        (startup/load paths only); runtime writes go through
        :meth:`_persist_snapshot` instead so the lock stays short."""
        self._write_snapshot(copy.deepcopy(self._state))

    def _persist_snapshot(self, snapshot: Dict[str, Any], *, only_keys: bool = False) -> None:
        """Write a snapshot to disk without holding the state lock (R41)."""
        self._write_snapshot(snapshot, only_keys=only_keys)

    def _write_snapshot(self, snapshot: Dict[str, Any], *, only_keys: bool = False) -> None:
        if self._persist_type == "memory":
            return
        with self._persist_lock:
            if self._persist_type == "sqlite" and self._sqlite_conn is not None:
                self._write_rows(snapshot)
                return
            if self._persist_type == "json":
                payload = snapshot
                if only_keys:
                    with self._lock:
                        payload = copy.deepcopy(self._state)
                self._persist_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self._persist_path.with_name(
                    f".{self._persist_path.name}.{threading.get_ident()}.tmp"
                )
                try:
                    tmp_path.write_text(
                        json.dumps(payload, ensure_ascii=True, indent=2),
                        encoding="utf-8",
                    )
                    os.replace(tmp_path, self._persist_path)
                except Exception:
                    if tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)
                    raise

    def _write_rows(self, rows: Dict[str, Any]) -> None:
        if self._sqlite_conn is None:
            return
        cur = self._sqlite_conn.cursor()
        for key, value in rows.items():
            cur.execute(
                "INSERT OR REPLACE INTO state(key, value_json) VALUES (?, ?)",
                (str(key), json.dumps(value, ensure_ascii=True)),
            )
        self._sqlite_conn.commit()

    def subscribe(self, listener: Callable[[str, Any], None]) -> None:
        if not callable(listener):
            return
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[str, Any], None]) -> None:
        with self._lock:
            self._listeners = [fn for fn in self._listeners if fn is not listener]

    def has_key(self, key: str) -> bool:
        with self._lock:
            return key in self._state

    def _notify(self, changes: Dict[str, Any]) -> None:
        if not self._pubsub_enabled or not changes:
            return
        with self._lock:
            listeners = list(self._listeners)
        for key, value in changes.items():
            for fn in listeners:
                try:
                    fn(key, value)
                except Exception as exc:
                    logger.warning("State listener for key %r raised: %s", key, exc)

    def get(self, key: Optional[str] = None, *, deep: bool = True) -> Any:
        # Fast copy/primitive return when key is requested, avoiding 798 fan-in full deepcopy churn
        with self._lock:
            if key is not None:
                val = self._state.get(key)
                if not deep or val is None or isinstance(val, (int, float, str, bool)):
                    return val
                return copy.deepcopy(val)
            if not deep:
                return dict(self._state)
            return copy.deepcopy(self._state)

    def _apply_updates(self, patch: Dict[str, Any]) -> None:
        changes: Dict[str, Any] = {}
        with self._lock:
            names: List[str] = []
            for key, value in patch.items():
                name = str(key)
                self._state[name] = value
                names.append(name)
                if name in self._pubsub_keys:
                    changes[name] = copy.deepcopy(value)
            snapshot = self._snapshot_locked(names)
        self._persist_snapshot(snapshot, only_keys=True)
        self._notify(changes)

    def update(self, patch: Dict[str, Any]) -> None:
        self._apply_updates(patch)

    def set_value(self, key: str, value: Any) -> None:
        self._apply_updates({str(key): value})

    def set_operational(self, val: str) -> None:
        self._apply_updates({"operational": val})

    def set_emotions(self, vals: List[str]) -> None:
        self._apply_updates({"emotions": list(vals)})
