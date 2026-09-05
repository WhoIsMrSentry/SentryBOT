from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

# Avoid touching numpy at all when the test runs on environments with a broken
# native build (e.g. experimental Python 3.14 + MINGW). The migrator already
# has a pure-Python fallback for ORB descriptors.
os.environ.setdefault("SENTRYBOT_DISABLE_NUMPY", "1")

from modules.cognitive_memory.db import SocialDB


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture()
def migrate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Patch the migrator to point at a temporary project root."""
    import scripts.migrations.social_db_migrate as migrate_mod

    monkeypatch.setattr(migrate_mod, "_ROOT", tmp_path)
    return migrate_mod


def test_migration_imports_all_sources(migrate, tmp_path: Path) -> None:
    pi_path = tmp_path / "modules" / "vlm_bridge" / "data" / "person_identity.json"
    faces_path = tmp_path / "data" / "faces.json"
    people_path = tmp_path / "data" / "people_memory.json"
    rel_path = tmp_path / "modules" / "autonomy" / "data" / "relationship_memory.json"

    _write_json(
        pi_path,
        {
            "abc123": {
                "name": "Emir",
                "recognition_level": 5,
                "relationship": "owner",
                "owner_priority": True,
                "trust_score": 0.9,
                "seen_count": 12,
                "conversation_notes": ["liked the joke", "coding together"],
            }
        },
    )

    zeros_row = [0] * 32
    _write_json(
        faces_path,
        {"Emir": {"descriptors": [zeros_row]}},
    )

    _write_json(
        people_path,
        {
            "Emir": {
                "chats": [
                    {"ts": 100, "role": "user", "text": "merhaba"},
                    {"ts": 200, "role": "assistant", "text": "selam"},
                ],
                "last_summary": {"text": "kahve sever", "ts": 250},
            }
        },
    )

    _write_json(
        rel_path,
        {
            "emir": {
                "name": "Emir",
                "is_owner": True,
                "last_emotion": "joy",
                "seen_count": 12,
                "chat_history": [{"ts": 300, "role": "user", "text": "muzik"}],
                "preferences": {"likes": ["kahve"], "topics": ["muzik"]},
                "moments": [{"text": "ilk gun", "score": 0.4, "created_at": 1, "updated_at": 1}],
            }
        },
    )

    db_path = tmp_path / "data" / "social.sqlite3"
    db = SocialDB(path=db_path, wal=False)
    try:
        n = 0
        n += migrate.migrate_person_identity(db, dry_run=False, keep=True)
        n += migrate.migrate_faces(db, dry_run=False, keep=True)
        n += migrate.migrate_people_memory(db, dry_run=False, keep=True)
        n += migrate.migrate_relationship_memory(db, dry_run=False, keep=True)
        assert n >= 4

        emir = db.persons.get_by_name("Emir")
        assert emir is not None
        assert emir["is_owner"] is True
        assert emir["recognition_level"] >= 5

        descriptors = db.face_descriptors.list_for_person(emir["id"], kind="orb")
        assert len(descriptors) == 1

        chats = db.chat_episodes.recent_for_person(emir["id"], limit=10)
        assert any(c["text"] == "muzik" for c in chats)

        rels = {row["key"]: row["value"] for row in db.relationships.list_for_person(emir["id"])}
        assert "likes" in rels and "kahve" in rels["likes"]

        moments = db.moments.list_for_person(emir["id"])
        texts = {m["text"] for m in moments}
        assert "kahve sever" in texts or any("kahve" in t for t in texts)
    finally:
        db.close()


def test_migration_is_idempotent(migrate, tmp_path: Path) -> None:
    pi_path = tmp_path / "modules" / "vlm_bridge" / "data" / "person_identity.json"
    _write_json(
        pi_path,
        {
            "abc123": {
                "name": "Twice",
                "recognition_level": 1,
                "relationship": "known",
                "trust_score": 0.2,
                "seen_count": 1,
            }
        },
    )

    db_path = tmp_path / "data" / "social.sqlite3"
    db = SocialDB(path=db_path, wal=False)
    try:
        migrate.migrate_person_identity(db, dry_run=False, keep=True)
        first_count = db.snapshot_stats()["persons"]
        migrate.migrate_person_identity(db, dry_run=False, keep=True)
        second_count = db.snapshot_stats()["persons"]
        assert first_count == second_count == 1
    finally:
        db.close()
