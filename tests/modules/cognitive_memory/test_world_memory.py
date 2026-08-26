from __future__ import annotations

from pathlib import Path
import pytest

from modules.cognitive_memory.db import SocialDB


@pytest.fixture()
def db(tmp_path: Path) -> SocialDB:
    target = tmp_path / "social.sqlite3"
    store = SocialDB(path=target, wal=False)
    try:
        yield store
    finally:
        store.close()


def test_world_memory_repo_upsert_and_get(db: SocialDB) -> None:
    rec = db.world_memory.upsert(
        memory_id="object:cup_1",
        kind="objects",
        name="blue cup",
        summary="A blue ceramic coffee mug on the desk.",
        details={"color": "blue", "material": "ceramic"},
        source="vlm",
        confidence=0.8,
        tags=["kitchen", "mug"],
    )
    assert rec["id"] == "object:cup_1"
    assert rec["name"] == "blue cup"
    assert rec["details"]["color"] == "blue"
    assert "kitchen" in rec["tags"]
    assert rec["observation_count"] == 1


def test_world_memory_repo_repeated_upsert_boosts_count(db: SocialDB) -> None:
    db.world_memory.upsert(
        memory_id="person:guest_1",
        kind="people",
        name="Guest",
        summary="A visitor seen near the entrance.",
        confidence=0.5,
    )
    second = db.world_memory.upsert(
        memory_id="person:guest_1",
        kind="people",
        name="Guest",
        summary="A visitor seen near the living room.",
        confidence=0.7,
    )
    assert second["observation_count"] == 2
    assert second["confidence"] >= 0.7


def test_world_memory_repo_observations_and_search(db: SocialDB) -> None:
    db.world_memory.upsert(
        memory_id="place:kitchen",
        kind="places",
        name="Kitchen",
        summary="The main kitchen area with refrigerator.",
        tags=["home", "food"],
    )
    obs_id = db.world_memory.record_observation(
        memory_id="place:kitchen",
        text="Light was turned on at 20:00",
        source="sensor",
    )
    assert obs_id > 0

    results = db.world_memory.search("refrigerator")
    assert len(results) == 1
    assert results[0]["id"] == "place:kitchen"

    by_kind = db.world_memory.list_by_kind("places")
    assert len(by_kind) == 1
