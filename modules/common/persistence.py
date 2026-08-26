"""Persistence Base Classes for SentryBOT.

Provides standardized persistence abstractions for SQLite, JSON, and in-memory storage.
Used by state_manager, cognitive_memory, and other modules needing persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Generic, Iterator, List, Optional, Type, TypeVar, Union

logger = logging.getLogger("common.persistence")

T = TypeVar("T")


@dataclass
class PersistenceConfig:
    """Configuration for persistence backends."""
    backend: str = "sqlite"  # sqlite, json, memory
    path: str = "data/persistence.db"
    # SQLite specific
    wal_mode: bool = True
    cache_size_kb: int = 4096
    busy_timeout_ms: int = 5000
    # JSON specific
    indent: int = 2
    auto_save: bool = True
    save_interval_s: float = 5.0
    # Common
    create_dirs: bool = True


class PersistenceError(Exception):
    """Base persistence exception."""
    pass


class PersistenceBackend(ABC, Generic[T]):
    """Abstract base class for persistence backends."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass
    
    @abstractmethod
    def get(self, key: str) -> Optional[T]:
        """Get value by key."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: T) -> None:
        """Set value for key."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key. Returns True if existed."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all data."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close backend (alias for disconnect)."""
        pass


class SQLiteBackend(PersistenceBackend[T]):
    """SQLite persistence backend with WAL mode support."""
    
    def __init__(self, config: PersistenceConfig, serializer: Optional[Callable[[T], str]] = None,
                 deserializer: Optional[Callable[[str], T]] = None):
        self.config = config
        self._serializer = serializer or json.dumps
        self._deserializer = deserializer or json.loads
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._initialized = False
    
    def connect(self) -> None:
        with self._lock:
            if self._initialized:
                return
            
            # Create directory if needed
            if self.config.create_dirs:
                Path(self.config.path).parent.mkdir(parents=True, exist_ok=True)
            
            self._conn = sqlite3.connect(
                self.config.path,
                check_same_thread=False,
                timeout=self.config.busy_timeout_ms / 1000.0,
            )
            self._conn.row_factory = sqlite3.Row
            
            # Enable WAL mode for better concurrency
            if self.config.wal_mode:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute(f"PRAGMA cache_size=-{self.config.cache_size_kb}")
                self._conn.execute(f"PRAGMA busy_timeout={self.config.busy_timeout_ms}")
            
            # Create table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kv_updated ON kv_store(updated_at)
            """)
            self._conn.commit()
            
            self._initialized = True
            logger.info("SQLite backend connected: %s", self.config.path)
    
    def disconnect(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                self._initialized = False
                logger.debug("SQLite backend disconnected")
    
    def close(self) -> None:
        self.disconnect()
    
    def _ensure_connected(self) -> None:
        if not self._initialized or self._conn is None:
            self.connect()
    
    def get(self, key: str) -> Optional[T]:
        self._ensure_connected()
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            try:
                return self._deserializer(row["value"])
            except Exception as e:
                logger.error("Failed to deserialize key %s: %s", key, e)
                return None
    
    def set(self, key: str, value: T) -> None:
        self._ensure_connected()
        with self._lock:
            serialized = self._serializer(value)
            now = time.time()
            self._conn.execute("""
                INSERT INTO kv_store (key, value, created_at, updated_at)
                VALUES (?, ?, 
                    COALESCE((SELECT created_at FROM kv_store WHERE key = ?), ?),
                    ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, serialized, key, now, now))
            self._conn.commit()
    
    def delete(self, key: str) -> bool:
        self._ensure_connected()
        with self._lock:
            cursor = self._conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            self._conn.commit()
            return cursor.rowcount > 0
    
    def exists(self, key: str) -> bool:
        self._ensure_connected()
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM kv_store WHERE key = ?", (key,)).fetchone()
            return row is not None
    
    def keys(self, pattern: str = "*") -> List[str]:
        self._ensure_connected()
        with self._lock:
            if pattern == "*":
                rows = self._conn.execute("SELECT key FROM kv_store ORDER BY key").fetchall()
            else:
                # Simple pattern matching (SQLite GLOB)
                sql_pattern = pattern.replace("*", "%").replace("?", "_")
                rows = self._conn.execute(
                    "SELECT key FROM kv_store WHERE key GLOB ? ORDER BY key", 
                    (sql_pattern,)
                ).fetchall()
            return [row["key"] for row in rows]
    
    def clear(self) -> None:
        self._ensure_connected()
        with self._lock:
            self._conn.execute("DELETE FROM kv_store")
            self._conn.commit()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class JSONBackend(PersistenceBackend[T]):
    """JSON file persistence backend with atomic writes."""
    
    def __init__(self, config: PersistenceConfig, serializer: Optional[Callable[[T], Any]] = None,
                 deserializer: Optional[Callable[[Any], T]] = None):
        self.config = config
        self._serializer = serializer or (lambda x: x)
        self._deserializer = deserializer or (lambda x: x)
        self._data: Dict[str, T] = {}
        self._lock = threading.RLock()
        self._dirty = False
        self._save_timer: Optional[threading.Timer] = None
        self._load()
    
    def _load(self) -> None:
        path = Path(self.config.path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        self._data = {k: self._deserializer(v) for k, v in raw.items()}
            except Exception as e:
                logger.warning("Failed to load JSON persistence: %s", e)
                self._data = {}
    
    def _save(self) -> None:
        if not self._dirty:
            return
        path = Path(self.config.path)
        if self.config.create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file then rename
        temp_path = path.with_suffix(".tmp")
        try:
            raw = {k: self._serializer(v) for k, v in self._data.items()}
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=self.config.indent, ensure_ascii=False)
            temp_path.replace(path)
            self._dirty = False
        except Exception as e:
            logger.error("Failed to save JSON persistence: %s", e)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    
    def _schedule_save(self) -> None:
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self.config.save_interval_s, self._save)
        self._save_timer.daemon = True
        self._save_timer.start()
    
    def connect(self) -> None:
        pass  # Already loaded in __init__
    
    def disconnect(self) -> None:
        if self._save_timer:
            self._save_timer.cancel()
        self._save()
    
    def close(self) -> None:
        self.disconnect()
    
    def get(self, key: str) -> Optional[T]:
        with self._lock:
            return self._data.get(key)
    
    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = value
            self._dirty = True
            if self.config.auto_save:
                self._schedule_save()
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._dirty = True
                if self.config.auto_save:
                    self._schedule_save()
                return True
            return False
    
    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            if pattern == "*":
                return list(self._data.keys())
            # Simple fnmatch-style pattern
            import fnmatch
            return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._dirty = True
            self._save()


class MemoryBackend(PersistenceBackend[T]):
    """In-memory persistence backend (for testing/development)."""
    
    def __init__(self, config: Optional[PersistenceConfig] = None):
        self.config = config or PersistenceConfig(backend="memory")
        self._data: Dict[str, T] = {}
        self._lock = threading.RLock()
    
    def connect(self) -> None:
        pass
    
    def disconnect(self) -> None:
        pass
    
    def close(self) -> None:
        pass
    
    def get(self, key: str) -> Optional[T]:
        with self._lock:
            return self._data.get(key)
    
    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            if pattern == "*":
                return list(self._data.keys())
            import fnmatch
            return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class PersistenceManager:
    """High-level persistence manager with backend abstraction."""
    
    def __init__(self, config: PersistenceConfig):
        self.config = config
        self._backend: Optional[PersistenceBackend] = None
        self._lock = threading.Lock()
    
    def _create_backend(self) -> PersistenceBackend:
        backend = self.config.backend.lower()
        if backend == "sqlite":
            return SQLiteBackend(self.config)
        elif backend == "json":
            return JSONBackend(self.config)
        elif backend == "memory":
            return MemoryBackend(self.config)
        else:
            raise ValueError(f"Unknown backend: {backend}")
    
    def get_backend(self) -> PersistenceBackend:
        with self._lock:
            if self._backend is None:
                self._backend = self._create_backend()
                self._backend.connect()
            return self._backend
    
    def get(self, key: str) -> Optional[T]:
        return self.get_backend().get(key)
    
    def set(self, key: str, value: T) -> None:
        self.get_backend().set(key, value)
    
    def delete(self, key: str) -> bool:
        return self.get_backend().delete(key)
    
    def exists(self, key: str) -> bool:
        return self.get_backend().exists(key)
    
    def keys(self, pattern: str = "*") -> List[str]:
        return self.get_backend().keys(pattern)
    
    def clear(self) -> None:
        self.get_backend().clear()
    
    def close(self) -> None:
        with self._lock:
            if self._backend:
                self._backend.close()
                self._backend = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience functions
def create_persistence(config: PersistenceConfig) -> PersistenceManager:
    """Create a persistence manager with the given config."""
    return PersistenceManager(config)


def create_sqlite_persistence(path: str, **kwargs) -> PersistenceManager:
    """Create SQLite persistence manager."""
    config = PersistenceConfig(backend="sqlite", path=path, **kwargs)
    return PersistenceManager(config)


def create_json_persistence(path: str, **kwargs) -> PersistenceManager:
    """Create JSON file persistence manager."""
    config = PersistenceConfig(backend="json", path=path, **kwargs)
    return PersistenceManager(config)


def create_memory_persistence() -> PersistenceManager:
    """Create in-memory persistence manager."""
    config = PersistenceConfig(backend="memory")
    return PersistenceManager(config)


__all__ = [
    "PersistenceConfig",
    "PersistenceBackend",
    "SQLiteBackend",
    "JSONBackend",
    "MemoryBackend",
    "PersistenceManager",
    "create_persistence",
    "create_sqlite_persistence",
    "create_json_persistence",
    "create_memory_persistence",
]