"""search_social_memory tool queries social_db preferences and moments."""

from __future__ import annotations

from pathlib import Path

from modules.agent_core.services.tools import ToolRegistry
from modules.agent_core.services.world_state import WorldState
from modules.cognitive_memory.db import SocialDB


class _FakeMemory:
    def search_memory(self, query, limit=5):
        return []


class _FakeSlam:
    def get_location(self):
        return "home"


def _registry(db: SocialDB):
    return ToolRegistry(
        client=None,
        memory=_FakeMemory(),
        slam=_FakeSlam(),
        world_state=WorldState(),
        safety_filter=None,
    )


def test_search_social_memory_returns_prefs_and_moments(tmp_path, monkeypatch):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    rec = db.persons.upsert(name="Emir", trust_score=0.65)
    db.relationships.set(rec["id"], "likes", "satranc,kahve")
    db.moments.add_or_boost(rec["id"], "likes:satranc", salience=0.7)
    monkeypatch.setattr("modules.cognitive_memory.get_default", lambda: db)
    reg = _registry(db)
    out = reg.search_social_memory("Emir", query="satranc")
    assert "trust_score=0.65" in out
    assert "satranc" in out


def test_search_social_memory_unknown_person(tmp_path, monkeypatch):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    monkeypatch.setattr("modules.cognitive_memory.get_default", lambda: db)
    reg = _registry(db)
    assert "No social record" in reg.search_social_memory("Nobody")
