"""SQLite schema definitions for the unified social store."""

from __future__ import annotations

SCHEMA_VERSION = 1

_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS persons (
        id TEXT PRIMARY KEY,
        canonical_name TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        recognition_level INTEGER NOT NULL DEFAULT 0,
        relationship TEXT NOT NULL DEFAULT 'unknown',
        is_owner INTEGER NOT NULL DEFAULT 0,
        owner_priority INTEGER NOT NULL DEFAULT 0,
        seen_count INTEGER NOT NULL DEFAULT 0,
        trust_score REAL NOT NULL DEFAULT 0.0,
        last_emotion TEXT NOT NULL DEFAULT '',
        last_distance_m REAL,
        first_seen_at REAL,
        last_seen_at REAL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        extra_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_persons_canonical ON persons(canonical_name)",
    "CREATE INDEX IF NOT EXISTS idx_persons_is_owner ON persons(is_owner)",
    """
    CREATE TABLE IF NOT EXISTS face_descriptors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        blob BLOB NOT NULL,
        rows INTEGER NOT NULL DEFAULT 0,
        cols INTEGER NOT NULL DEFAULT 0,
        score REAL NOT NULL DEFAULT 0.0,
        created_at REAL NOT NULL,
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_face_desc_person ON face_descriptors(person_id, kind)",
    """
    CREATE TABLE IF NOT EXISTS sightings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        ts REAL NOT NULL,
        source TEXT NOT NULL DEFAULT '',
        mood TEXT NOT NULL DEFAULT '',
        distance_m REAL,
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sightings_person_ts ON sightings(person_id, ts)",
    """
    CREATE TABLE IF NOT EXISTS chat_episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        ts REAL NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        text TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_person_ts ON chat_episodes(person_id, ts)",
    """
    CREATE TABLE IF NOT EXISTS relationships (
        person_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (person_id, key),
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS moments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        ts REAL NOT NULL,
        kind TEXT NOT NULL DEFAULT 'note',
        text TEXT NOT NULL,
        score REAL NOT NULL DEFAULT 0.0,
        updated_at REAL NOT NULL,
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_moments_person_score ON moments(person_id, score)",
    """
    CREATE TABLE IF NOT EXISTS mood_snapshots (
        ts REAL PRIMARY KEY,
        happiness REAL,
        energy REAL,
        curiosity REAL,
        fear REAL,
        dominant TEXT NOT NULL DEFAULT 'neutral'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rituals (
        day TEXT NOT NULL,
        kind TEXT NOT NULL,
        done_at REAL NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (day, kind)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interaction_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        kind TEXT NOT NULL,
        count_inc INTEGER NOT NULL DEFAULT 1,
        payload_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inter_events_ts ON interaction_events(ts)",
    "CREATE INDEX IF NOT EXISTS idx_inter_events_kind ON interaction_events(kind, ts)",
    """
    CREATE TABLE IF NOT EXISTS owner_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_ts REAL NOT NULL,
        end_ts REAL,
        source TEXT NOT NULL DEFAULT '',
        authority_level INTEGER NOT NULL DEFAULT 5,
        notes TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_owner_sessions_start ON owner_sessions(start_ts)",
)


def get_ddl() -> tuple[str, ...]:
    """Return the ordered tuple of DDL statements for the current schema."""
    return _DDL
