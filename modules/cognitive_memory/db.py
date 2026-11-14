"""SQLite connection and aggregator for the unified social store.

The :class:`SocialDB` owns a single threadsafe connection (``check_same_thread``
disabled) protected by a :class:`threading.RLock`. Repositories are attached as
attributes and share the underlying connection. The store creates the schema
lazily on first use.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional

from .schema import SCHEMA_VERSION, get_ddl
from .utils import backup_sqlite_connection, resolve_repo_path
from .repositories.persons import PersonsRepo
from .repositories.face_descriptors import FaceDescriptorsRepo
from .repositories.sightings import SightingsRepo
from .repositories.chat_episodes import ChatEpisodesRepo
from .repositories.relationships import RelationshipsRepo
from .repositories.moments import MomentsRepo
from .repositories.mood_snapshots import MoodSnapshotsRepo
from .repositories.rituals import RitualsRepo
from .repositories.interaction_events import InteractionEventsRepo
from .repositories.owner_sessions import OwnerSessionsRepo
from .repositories.world_memory import WorldMemoryRepo

logger = logging.getLogger("social_db")

_DEFAULT_LOCK = threading.RLock()
_DEFAULT: Optional["SocialDB"] = None


class SocialDB:
    """Aggregates SQLite repositories for the social/identity domain."""

    def __init__(
        self,
        path: str | Path = "data/social.sqlite3",
        *,
        wal: bool = True,
        cache_size_kb: int = 4096,
        busy_timeout_ms: int = 5000,
        auto_migrate: bool = True,
    ) -> None:
        self.path = self._resolve_path(path)
        self._lock = threading.RLock()
        self._closed = False
        self._tx_depth = threading.local()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,
            timeout=max(0.1, busy_timeout_ms / 1000.0),
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        if wal:
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error as exc:
                logger.debug("WAL mode unavailable: %s", exc)
        try:
            self._conn.execute(f"PRAGMA cache_size = -{int(max(64, cache_size_kb))}")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as exc:
            logger.debug("PRAGMA tuning failed: %s", exc)

        if auto_migrate:
            self._migrate()

        self.persons = PersonsRepo(self)
        self.face_descriptors = FaceDescriptorsRepo(self)
        self.sightings = SightingsRepo(self)
        self.chat_episodes = ChatEpisodesRepo(self)
        self.relationships = RelationshipsRepo(self)
        self.moments = MomentsRepo(self)
        self.mood_snapshots = MoodSnapshotsRepo(self)
        self.rituals = RitualsRepo(self)
        self.interaction_events = InteractionEventsRepo(self)
        self.owner_sessions = OwnerSessionsRepo(self)
        self.world_memory = WorldMemoryRepo(self)

    def purge_old_data(self, max_age_days: float = 7.0) -> Dict[str, int]:
        s_count = self.sightings.purge_older_than(max_age_days)
        i_count = self.interaction_events.prune_older_than(max_age_days)
        return {"purged_sightings": s_count, "purged_interaction_events": i_count}

    def close(self) -> None:
        global _DEFAULT
        with self._lock:
            self._closed = True
            try:
                self._conn.close()
            except Exception:
                pass
        with _DEFAULT_LOCK:
            if _DEFAULT is self:
                _DEFAULT = None

    @staticmethod
    def _resolve_path(path: str | Path) -> Path:
        return resolve_repo_path(path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block under an exclusive transaction; supports re-entrant nesting via thread-local _tx_depth."""
        with self._lock:
            depth = int(getattr(self._tx_depth, "count", 0))
            if depth > 0:
                self._tx_depth.count = depth + 1
                try:
                    yield self._conn
                finally:
                    self._tx_depth.count = depth
                return

            cur = self._conn.cursor()
            self._tx_depth.count = 1
            try:
                cur.execute("BEGIN IMMEDIATE")
                yield self._conn
                cur.execute("COMMIT")
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            finally:
                self._tx_depth.count = 0
                cur.close()

    def backup(self, dest_path: str | Path) -> Path:
        """Create a consistent online SQLite backup using Connection.backup()."""
        return backup_sqlite_connection(self._conn, self._lock, dest_path)

    def execute(self, sql: str, params: tuple | list | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq: list[tuple] | list[dict]) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq)

    def fetchone(self, sql: str, params: tuple | list | dict = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            try:
                return cur.fetchone()
            finally:
                cur.close()

    def fetchall(self, sql: str, params: tuple | list | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            try:
                return cur.fetchall()
            finally:
                cur.close()

    def snapshot_stats(self) -> Dict[str, int]:
        """Return row counts for monitoring and admin UI surfaces."""
        out: Dict[str, int] = {}
        tables = (
            "persons",
            "face_descriptors",
            "sightings",
            "chat_episodes",
            "relationships",
            "moments",
            "mood_snapshots",
            "rituals",
            "interaction_events",
            "owner_sessions",
            ("world_memory", "world_memories"),
        )
        for tbl in tables:
            key, sql_tbl = tbl if isinstance(tbl, tuple) else (tbl, tbl)
            try:
                row = self.fetchone(f"SELECT COUNT(*) AS n FROM {sql_tbl}")
                out[key] = int(row["n"]) if row else 0
            except Exception:
                out[key] = 0
        out["schema_version"] = SCHEMA_VERSION
        return out

    def _migrate(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            try:
                for stmt in get_ddl():
                    cur.execute(stmt)
                try:
                    cur.execute("ALTER TABLE world_memories ADD COLUMN expiry REAL NOT NULL DEFAULT 0.0")
                except sqlite3.OperationalError:
                    pass
                cur.execute(
                    "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, time.time()),
                )
            finally:
                cur.close()


def get_default() -> Optional[SocialDB]:
    """Return the process-wide default :class:`SocialDB`, if registered and open."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is not None and getattr(_DEFAULT, "_closed", False):
            _DEFAULT = None
        return _DEFAULT


def set_default(db: SocialDB) -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = db


def reset_default() -> None:
    """Clear the process-wide default. Used by tests."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        db = _DEFAULT
        _DEFAULT = None
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
