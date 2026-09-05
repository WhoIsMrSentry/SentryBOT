"""Tests for dialogue fact consolidation."""

from __future__ import annotations

from modules.agent_core.services.memory_consolidator import MemoryConsolidator


class _FakeMemory:
    def __init__(self):
        self.stored = []

    def remember(self, event_type, content, importance=1):
        self.stored.append((event_type, content, importance))


def test_extract_name_fact_turkish_and_english():
    c = MemoryConsolidator()
    assert "user name is Emir" in c.extract_facts("User: benim adim Emir | Bot: selam")
    assert "user name is Sarah" in c.extract_facts("my name is Sarah")


def test_extract_pet_and_location():
    c = MemoryConsolidator()
    assert "user has a pet named Max" in c.extract_facts("my dog is Max")
    assert "user lives in Izmir" in c.extract_facts("i live in Izmir")


def test_consolidate_stores_high_importance_facts():
    mem = _FakeMemory()
    c = MemoryConsolidator(memory=mem)
    facts = c.consolidate("User: benim adim Emir | Bot: merhaba")
    assert facts == ["user name is Emir"]
    assert mem.stored and mem.stored[0][0] == "fact"
    assert mem.stored[0][2] >= 5  # stored with high importance


def test_no_facts_is_noop():
    mem = _FakeMemory()
    c = MemoryConsolidator(memory=mem)
    assert c.consolidate("User: hava bugun nasil | Bot: guzel") == []
    assert mem.stored == []


def test_consolidate_mirrors_fact_to_social_db(tmp_path):
    from modules.cognitive_memory.db import SocialDB

    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    mem = _FakeMemory()
    c = MemoryConsolidator(memory=mem, social_db=db)
    facts = c.consolidate("benim adim Emir", speaker="Emir")
    assert facts == ["user name is Emir"]
    rec = db.persons.get_by_name("Emir")
    assert rec is not None
    moments = db.moments.top_for_person(rec["id"], limit=5)
    assert any("user name is Emir" in str(m.get("text", "")) for m in moments)
