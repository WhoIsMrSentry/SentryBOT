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
from typing import Any, Dict, Iterator, Optional

from .schema import SCHEMA_VERSION, get_ddl

logger = logging.getLogger("social_db")

_DEFAULT_LOCK = threading.Lock()
_DEFAULT: Optional["SocialDB"] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    @staticmethod
    def _resolve_path(path: str | Path) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return (_project_root() / p).resolve()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block under an exclusive transaction. Reuses the shared connection."""
        with self._lock:
            cur = self._conn.cursor()
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
                cur.close()

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
        )
        for tbl in tables:
            try:
                row = self.fetchone(f"SELECT COUNT(*) AS n FROM {tbl}")
                out[tbl] = int(row["n"]) if row else 0
            except Exception:
                out[tbl] = 0
        out["schema_version"] = SCHEMA_VERSION
        return out

    def _migrate(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            try:
                for stmt in get_ddl():
                    cur.execute(stmt)
                cur.execute(
                    "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, time.time()),
                )
            finally:
                cur.close()


def get_default() -> Optional[SocialDB]:
    """Return the process-wide default :class:`SocialDB`, if registered."""
    with _DEFAULT_LOCK:
        return _DEFAULT


def set_default(db: SocialDB) -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = db


def reset_default() -> None:
    """Clear the process-wide default. Used by tests."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is not None:
            try:
                _DEFAULT.close()
            except Exception:
                pass
        _DEFAULT = None
