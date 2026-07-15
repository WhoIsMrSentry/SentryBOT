from __future__ import annotations

import time
from pathlib import Path

import pytest

from modules.social_db.db import SocialDB


@pytest.fixture()
def db(tmp_path: Path) -> SocialDB:
    target = tmp_path / "social.sqlite3"
    store = SocialDB(path=target, wal=False)
    try:
        yield store
    finally:
        store.close()


def test_persons_upsert_dedup_by_canonical_name(db: SocialDB) -> None:
    first = db.persons.upsert(name="Emir", trust_score=0.2)
    second = db.persons.upsert(name="emir ", trust_score=0.5, increment_seen=True)
    assert first["id"] == second["id"]
    assert second["seen_count"] == 1
    assert pytest.approx(second["trust_score"], rel=1e-3) == 0.5


def test_persons_set_owner_flags(db: SocialDB) -> None:
    rec = db.persons.set_owner("Emir")
    assert rec["is_owner"] is True
    assert rec["recognition_level"] >= 5
    owner = db.persons.get_owner()
    assert owner is not None and owner["id"] == rec["id"]


def test_chat_episodes_pruning(db: SocialDB) -> None:
    rec = db.persons.upsert(name="Tester")
    pid = rec["id"]
    for idx in range(20):
        db.chat_episodes.append(person_id=pid, role="user", text=f"hi {idx}", ts=time.time() + idx)
    removed = db.chat_episodes.prune_for_person(pid, keep_last=5)
    assert removed == 15
    kept = db.chat_episodes.recent_for_person(pid, limit=10)
    assert len(kept) == 5
    assert kept[-1]["text"] == "hi 19"


def test_face_descriptors_replace(db: SocialDB) -> None:
    rec = db.persons.upsert(name="Face")
    pid = rec["id"]
    db.face_descriptors.replace_for_person(pid, "orb", b"abcd", rows=1, cols=4)
    db.face_descriptors.replace_for_person(pid, "orb", b"efgh", rows=1, cols=4)
    rows = db.face_descriptors.list_for_person(pid, kind="orb")
    assert len(rows) == 1
    assert bytes(rows[0]["blob"]) == b"efgh"


def test_moments_decay(db: SocialDB) -> None:
    rec = db.persons.upsert(name="Mood")
    pid = rec["id"]
    db.moments.add_or_boost(pid, "loves coffee", salience=0.5)
    db.moments.add_or_boost(pid, "loves coffee", salience=0.5)
    rows = db.moments.list_for_person(pid)
    assert len(rows) == 1
    assert rows[0]["score"] == pytest.approx(1.0)


def test_interaction_events_counts(db: SocialDB) -> None:
    db.interaction_events.log("hello", count_inc=1)
    db.interaction_events.log("hello", count_inc=2)
    db.interaction_events.log("bye", count_inc=1)
    counts = db.interaction_events.counts()
    assert counts.get("hello") == 3
    assert counts.get("bye") == 1


def test_rituals_idempotent(db: SocialDB) -> None:
    db.rituals.mark_done("morning")
    assert db.rituals.is_done("morning")
    db.rituals.mark_done("morning")
    rows = db.rituals.list_for_day()
    assert len(rows) == 1


def test_owner_sessions(db: SocialDB) -> None:
    sid = db.owner_sessions.start(source="rfid")
    active = db.owner_sessions.active()
    assert active is not None and active["id"] == sid
    db.owner_sessions.end(sid)
    assert db.owner_sessions.active() is None


def test_snapshot_stats_includes_schema_version(db: SocialDB) -> None:
    db.persons.upsert(name="Stat")
    stats = db.snapshot_stats()
    assert stats.get("persons", 0) >= 1
    assert stats.get("schema_version") == 1
