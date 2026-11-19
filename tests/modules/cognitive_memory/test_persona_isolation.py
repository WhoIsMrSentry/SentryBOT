"""Tests for per-persona isolation across EpisodicMemory, ChatRAG, WorldMemory, and SocialDB."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import time

import pytest

from modules.agent_core.services.memory import EpisodicMemory
from modules.cognitive_memory.db import SocialDB
from modules.cognitive_memory.schema import SCHEMA_VERSION
from modules.cognitive_memory.services.chat_rag import ChatRAG
from modules.cognitive_memory.services.relationship_memory import RelationshipMemory
from modules.cognitive_memory.services.world_memory import WorldMemory
from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG
from modules.common.persona_scope import DEFAULT_PERSONA_ID, persona_context, set_active_persona


@pytest.fixture(autouse=True)
def _reset_persona_scope():
    set_active_persona(DEFAULT_PERSONA_ID, notify=False)
    yield
    set_active_persona(DEFAULT_PERSONA_ID, notify=False)


def test_episodic_memory_isolated_per_persona(tmp_path: Path) -> None:
    mem = EpisodicMemory(db_path=str(tmp_path / "episodes.db"))
    with persona_context("sentry"):
        mem.remember("fact", "Emir loves Turkish filter coffee", importance=8)
    with persona_context("glados"):
        mem.remember("fact", "Test subject prefers potato batteries", importance=8)

    with persona_context("sentry"):
        s_hits = mem.search_memory("coffee", limit=5)
        s_cross = mem.search_memory("potato", limit=5)
    with persona_context("glados"):
        g_hits = mem.search_memory("potato", limit=5)
        g_cross = mem.search_memory("coffee", limit=5)

    assert any("Turkish filter coffee" in x["content"] for x in s_hits)
    assert all("potato batteries" not in x["content"] for x in s_cross)
    assert any("potato batteries" in x["content"] for x in g_hits)
    assert all("Turkish filter coffee" not in x["content"] for x in g_cross)


def test_chat_rag_and_day_summaries_isolated_per_persona(tmp_path: Path) -> None:
    rag = ChatRAG({"db_path": str(tmp_path / "chat_rag.sqlite3")})
    try:
        with persona_context("sentry"):
            assert rag.ingest(person_id="p1", role="user", text="bugün çay demledik", ts=1000.0)
            assert rag.remember_day_summary(person_id="p1", day="2026-11-19", text="Sentry çay sohbeti")
        with persona_context("glados"):
            assert rag.ingest(person_id="p1", role="user", text="aperture science cake testing", ts=1000.0)
            assert rag.remember_day_summary(person_id="p1", day="2026-11-19", text="GLaDOS test günü")

        with persona_context("sentry"):
            s_chat = rag.recall("cake", person_id="p1", limit=5)
            s_sum = rag.day_summaries(person_id="p1")
            assert all("cake" not in item["text"].lower() for item in s_chat)
            assert s_sum[0]["text"] == "Sentry çay sohbeti"

        with persona_context("glados"):
            g_chat = rag.recall("cake", person_id="p1", limit=5)
            g_sum = rag.day_summaries(person_id="p1")
            assert any("cake" in item["text"].lower() for item in g_chat)
            assert g_sum[0]["text"] == "GLaDOS test günü"
    finally:
        rag.close()


def test_world_memory_and_rag_isolated_per_persona(tmp_path: Path) -> None:
    rag = WorldMemoryRAG({"db_path": str(tmp_path / "world_rag.sqlite3")})
    wm = WorldMemory(
        {
            "persistence_enabled": True,
            "storage_path": str(tmp_path / "world_memory.json"),
            "rag_backing": rag,
        }
    )
    try:
        with persona_context("sentry"):
            wm.observe({"kind": "fact", "name": "dessert", "summary": "Baklava en iyi tatlıdır"})
        with persona_context("glados"):
            wm.observe({"kind": "fact", "name": "dessert", "summary": "The cake is definitely a lie"})

        with persona_context("sentry"):
            s_rag = rag.recall("dessert")
            assert len(s_rag["items"]) == 1
            assert "Baklava" in s_rag["items"][0]["summary"]
            assert wm.status()["total"] == 1

        with persona_context("glados"):
            g_rag = rag.recall("dessert")
            assert len(g_rag["items"]) == 1
            assert "cake is definitely a lie" in g_rag["items"][0]["summary"]
            assert wm.status()["total"] == 1

        # JSON reload preserves per-persona stores
        wm2 = WorldMemory(
            {
                "persistence_enabled": True,
                "storage_path": str(tmp_path / "world_memory.json"),
            }
        )
        with persona_context("glados"):
            assert "cake is definitely a lie" in wm2.recent(limit=5)["items"][0]["summary"]
        with persona_context("sentry"):
            assert "Baklava" in wm2.recent(limit=5)["items"][0]["summary"]
    finally:
        rag.close()


def test_social_db_v1_migration_and_shared_person_split_relationship(tmp_path: Path) -> None:
    db_file = tmp_path / "legacy_social.sqlite3"
    now = time.time()
    # Create an old v1 database before persona_id columns existed
    con = sqlite3.connect(str(db_file))
    con.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
        INSERT INTO schema_version(version, applied_at) VALUES (1, 100.0);
        CREATE TABLE persons (
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
        );
        CREATE TABLE chat_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            ts REAL NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            text TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE relationships (
            person_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (person_id, key)
        );
        CREATE TABLE moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            ts REAL NOT NULL,
            kind TEXT NOT NULL DEFAULT 'note',
            text TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            updated_at REAL NOT NULL
        );
        """
    )
    con.execute(
        "INSERT INTO persons(id, canonical_name, display_name, is_owner, created_at, updated_at) VALUES ('p_emir', 'emir', 'Emir', 1, ?, ?)",
        (now, now),
    )
    con.execute(
        "INSERT INTO relationships(person_id, key, value, updated_at) VALUES ('p_emir', 'likes', 'robotik', ?)",
        (now,),
    )
    con.commit()
    con.close()

    sdb = SocialDB(path=db_file, wal=False)
    try:
        assert sdb.snapshot_stats()["schema_version"] == SCHEMA_VERSION
        rel_mem = RelationshipMemory(enabled=True, social_db=sdb)

        # Shared identity remains visible in GLaDOS without duplicating Emir in persons
        with persona_context("glados"):
            assert rel_mem.classify_person("Emir") == "owner"
            sdb.relationships.set("p_emir", "likes", "testing")
            rel_mem.add_chat("Emir", "user", "test odasını aç")

        with persona_context("sentry"):
            s_rels = {r["key"]: r["value"] for r in sdb.relationships.list_for_person("p_emir")}
            assert s_rels["likes"] == "robotik"
            rel_mem.add_chat("Emir", "user", "günaydın sentry")
            assert rel_mem.last_user_utterance("Emir") == "günaydın sentry"

        with persona_context("glados"):
            g_rels = {r["key"]: r["value"] for r in sdb.relationships.list_for_person("p_emir")}
            assert g_rels["likes"] == "testing"
            assert rel_mem.last_user_utterance("Emir") == "test odasını aç"

        assert len(sdb.persons.top_people(limit=10)) == 1
    finally:
        sdb.close()


def test_relationship_memory_json_fallback_shares_identity_isolates_history(tmp_path: Path) -> None:
    rel = RelationshipMemory(enabled=True, path=str(tmp_path / "rel.json"), social_db=False)
    with persona_context("sentry"):
        rel.observe_person("Emir", is_owner=True, emotion="joy")
        rel.add_chat("Emir", "user", "kahveyi severim")
    with persona_context("glados"):
        assert rel.classify_person("Emir") == "owner"
        rel.add_chat("Emir", "user", "portal gun hazır mı")
        assert rel.last_user_utterance("Emir") == "portal gun hazır mı"
    with persona_context("sentry"):
        assert rel.last_user_utterance("Emir") == "kahveyi severim"
