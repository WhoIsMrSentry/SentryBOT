from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import time

import numpy as np
import pytest

from modules.cognitive_memory.config_loader import load_config
from modules.cognitive_memory.db import SocialDB
from modules.cognitive_memory.services.chat_rag import ChatRAG
from modules.cognitive_memory.services.people_memory import PeopleMemory
from modules.cognitive_memory.services.relationship_memory import RelationshipMemory
from modules.cognitive_memory.services.sleep_consolidator import SleepConsolidator
from modules.cognitive_memory.services.world_memory import WorldMemory
from modules.cognitive_memory.services.world_memory_rag import (
    WorldMemoryRAG,
    get_default as get_world_rag_default,
    reset_default as reset_world_rag_default,
)


def test_social_db_nested_transactions_stats_backup_and_config(tmp_path: Path) -> None:
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    try:
        # Nested transaction must work on the same thread without OperationalError
        with db.transaction():
            rec = db.persons.upsert(name="Ali", trust_score=0.4)
            pid = rec["id"]
            before_seen = rec["last_seen_at"]
            with db.transaction():
                db.moments.add_or_boost(pid, "likes robotics", salience=0.6)
                new_trust = db.persons.adjust_trust(pid, 0.2)
            db.world_memory.upsert(
                memory_id="fact:sky",
                kind="fact",
                name="sky",
                summary="sky is blue",
            )

        assert new_trust == pytest.approx(0.6)
        assert db.persons.get_by_id(pid)["last_seen_at"] == before_seen
        assert db.snapshot_stats()["world_memory"] == 1

        # Exponential decay verification (t = 1 half-life => score / 2)
        db.execute(
            "UPDATE moments SET score = 0.8, updated_at = ? WHERE person_id = ?",
            (time.time() - 100.0, pid),
        )
        db.moments.decay(pid, half_life_s=100.0)
        decayed_rows = db.moments.list_for_person(pid)
        assert len(decayed_rows) == 1
        assert math.isclose(decayed_rows[0]["score"], 0.4, rel_tol=0.05)

        # Deterministic ts DESC, id DESC tie ordering on chat_episodes
        fixed_ts = 1700000000.0
        for msg in ("m1", "m2", "m3"):
            db.chat_episodes.append(person_id=pid, role="user", text=msg, ts=fixed_ts)
        db.chat_episodes.prune_for_person(pid, keep_last=2)
        recent = db.chat_episodes.recent_for_person(pid, limit=5)
        assert [r["text"] for r in recent] == ["m2", "m3"]

        # Online SQLite backup (Feature L43)
        bkp = db.backup(tmp_path / "backups" / "social.backup")
        assert bkp.exists()
        con = sqlite3.connect(str(bkp))
        cnt = con.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        con.close()
        assert cnt == 1
    finally:
        db.close()

    override_yml = tmp_path / "mem.yml"
    override_yml.write_text("busy_timeout_ms: 9000\nworld_memory:\n  max_context_items: 12\n", encoding="utf-8")
    loaded = load_config(str(override_yml))
    assert int(loaded["busy_timeout_ms"]) == 9000
    assert int(loaded["world_memory"]["max_context_items"]) == 12


def test_world_memory_rag_fts_no_rebuild_quotes_expiry_and_backfill(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "wm_rag.sqlite3"
    rag = WorldMemoryRAG({"db_path": str(db_file), "enabled": True})
    try:
        rag.observe(
            {"kind": "fact", "name": "coffee_pref", "summary": "Emir likes dark espresso!", "tags": ["drink"]},
            now=1000.0,
        )
        rag.observe(
            {
                "kind": "event",
                "name": "expired_event",
                "summary": "temp coffee alert",
                "expiry": 1005.0,
            },
            now=1000.0,
        )
        # Punctuation / FTS keyword operators must not break MATCH
        res = rag.recall("coffee-pref! NOT tea OR", now=1010.0)
        ids = [item["id"] for item in res["items"]]
        assert "fact:coffee_pref" in ids
        assert "event:expired_event" not in ids

        # Supersedes removes stale entry (observed without embed_fn -> embed_state=0)
        rag.set_embedding_provider(None)
        rag.observe(
            {
                "kind": "fact",
                "name": "coffee_v2",
                "summary": "Emir prefers oat latte now",
                "supersedes": "fact:coffee_pref",
            },
            now=1020.0,
        )
        assert rag.get("fact:coffee_pref", now=1020.0) == {}

        # Feature L43: backfill_embeddings computes missing embed_state=0 vectors + online backup
        calls = {"n": 0}

        def _embed(txt: str):
            calls["n"] += 1
            return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        rag.set_embedding_provider(_embed)
        filled = rag.backfill_embeddings(batch_size=10)
        assert filled >= 1 and calls["n"] >= 1
        assert rag.status(now=1020.0)["unembedded"] == 0

        recalled = rag.recall("oat latte", now=1020.0)
        assert recalled["items"] and recalled["items"][0]["id"] == "fact:coffee_v2"

        bkp = rag.backup(tmp_path / "wm_rag.backup")
        assert bkp.exists()
    finally:
        rag.close()

    # Reopening non-empty FTS DB must NOT rebuild memories_fts
    rebuilt = []
    monkeypatch.setattr(WorldMemoryRAG, "_rebuild_fts", lambda self, _con: rebuilt.append(True))
    rag2 = WorldMemoryRAG({"db_path": str(db_file), "enabled": True})
    try:
        assert rebuilt == []
    finally:
        rag2.close()


def test_world_memory_expiry_supersedes_and_shared_singleton(tmp_path: Path) -> None:
    reset_world_rag_default()
    rag = get_world_rag_default({"db_path": str(tmp_path / "shared_wm.sqlite3"), "enabled": True})
    try:
        wm = WorldMemory({"storage_path": str(tmp_path / "wm.json"), "persistence_enabled": True, "rag_backing": rag})
        wm.observe({"kind": "object", "name": "old_cup", "summary": "red cup"}, now=100.0)
        wm.observe({"kind": "event", "name": "temp_door", "summary": "door open", "expiry_s": 5.0}, now=100.0)
        wm.observe({"kind": "object", "name": "new_cup", "summary": "blue mug", "supersedes": "objects:old_cup"}, now=102.0)

        recent = wm.recent(now=110.0)
        names = [x["name"] for x in recent["items"]]
        assert "new_cup" in names
        assert "old_cup" not in names
        assert "temp_door" not in names
        assert wm.get("events:temp_door_api", now=110.0)["available"] is False
        assert rag.get("objects:new_cup", now=110.0)["name"] == "new_cup"
    finally:
        reset_world_rag_default()


def test_chat_rag_sql_filter_norm_backfill_and_backup(tmp_path: Path) -> None:
    rag = ChatRAG({"db_path": str(tmp_path / "chat.sqlite3"), "enabled": True})
    try:
        # Insert 1 target chunk for alice and many chunks for bob with matching keyword
        rag.ingest(person_id="alice", role="user", text="robot sensor status check", ts=100.0, kind="chat")
        for idx in range(25):
            rag.ingest(person_id="bob", role="user", text=f"robot status noise {idx}", ts=200.0 + idx, kind="chat")

        # SQL-pushed person_id filter guarantees alice finds her own message cleanly
        alice_hits = rag.recall("robot", person_id="alice", limit=3, kinds=["chat"])
        assert len(alice_hits) == 1
        assert alice_hits[0]["person_id"] == "alice"

        # Mismatched + valid normalized vectors via backfill_embeddings (Feature L43)
        rag.set_embedding_provider(lambda txt: np.array([3.0, 4.0], dtype=np.float32))
        filled = rag.backfill_embeddings(batch_size=5)
        assert filled == 5

        reranked = rag.recall("robot sensor", person_id="alice", limit=3)
        assert len(reranked) == 1

        bkp = rag.backup(tmp_path / "chat.backup")
        assert bkp.exists()
    finally:
        rag.close()


def test_relationship_memory_people_memory_and_sleep_consolidator(tmp_path: Path, monkeypatch) -> None:
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    chat_rag = ChatRAG({"db_path": str(tmp_path / "chat_rag.sqlite3"), "enabled": True})
    world_rag = WorldMemoryRAG({"db_path": str(tmp_path / "world_rag.sqlite3"), "enabled": True})
    try:
        rel = RelationshipMemory(social_db=db)
        assert not hasattr(rel, "get_relationship_personality_bias")

        # Avoid touching global ChatRAG singleton
        monkeypatch.setattr("modules.cognitive_memory.services.chat_rag.get_default", lambda: chat_rag)

        rel.add_chat("Zeynep", "user", "Seviyorum kahve ama sevmiyorum gurultu.")
        rec = rel.get("Zeynep")
        assert rec is not None

        # social_profile() must be strictly read-only (no decay write on read!)
        decay_calls = []
        orig_decay = db.moments.decay
        monkeypatch.setattr(db.moments, "decay", lambda pid: (decay_calls.append(pid), orig_decay(pid))[1])
        prof = rel.social_profile("Zeynep")
        assert prof["name"] == "Zeynep"
        assert decay_calls == []

        # PeopleMemory atomic JSON write
        pm = PeopleMemory(data_dir=str(tmp_path / "pm"), filename="pm.json", social_db=False)
        pm.append_chat("Kaan", "user", "selam")
        pm.set_summary("Kaan", "selamlama")
        assert (tmp_path / "pm" / "pm.json").exists()
        assert list((tmp_path / "pm").glob("*.tmp.*")) == []

        # SleepConsolidator actually invokes SocialDB.moments.decay + ChatRAG.remember_day_summary + backfill + backup
        world_rag.set_embedding_provider(None)
        world_rag.observe({"kind": "object", "name": "lamp", "summary": "desk lamp"})
        chat_rag.set_embedding_provider(lambda _t: [1.0, 0.0, 0.0])
        world_rag.set_embedding_provider(lambda _t: [1.0, 0.0, 0.0])

        sc = SleepConsolidator(social_db=db, chat_rag=chat_rag, world_rag=world_rag)
        now = 1700001000.0
        res = sc.consolidate_session(
            [{"user": "Zeynep", "text": "Bugun kahve ictik", "importance": 2.0, "timestamp": now - 60}],
            current_time_s=now,
            person_id=rec["id"],
            day="2026-11-16",
        )
        assert res["summary_saved"] is True
        assert len(decay_calls) == 1
        assert len(chat_rag.day_summaries(person_id=rec["id"])) == 1

        maint = sc.run_maintenance(backup_dir=tmp_path / "sleep_bkps")
        assert maint["ok"] is True
        assert maint["chat_backfilled"] >= 1
        assert maint["world_backfilled"] >= 1
        assert len(maint["backups"]) == 3
    finally:
        world_rag.close()
        chat_rag.close()
        db.close()
