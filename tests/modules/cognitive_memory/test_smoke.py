"""Smoke test for the social_db module.

Verifies that a fresh SocialDB instance migrates its schema without error
and closes cleanly.
"""

from __future__ import annotations

from pathlib import Path

from modules.cognitive_memory.db import SocialDB
from modules.cognitive_memory.schema import SCHEMA_VERSION


def test_social_db_migrates_and_closes_cleanly(tmp_path: Path) -> None:
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    try:
        stats = db.snapshot_stats()
        assert stats.get("schema_version") == SCHEMA_VERSION
        assert db.persons is not None
    finally:
        db.close()
