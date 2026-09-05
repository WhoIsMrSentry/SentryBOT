"""RelationshipMemory: preferences, social_profile and recall candidates."""

from __future__ import annotations

from pathlib import Path

from modules.cognitive_memory.services.relationship_memory import RelationshipMemory
from modules.cognitive_memory.db import SocialDB


def _rm_with_db(tmp_path: Path):
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    rm = RelationshipMemory(enabled=True, social_db=db)
    return rm, db


def test_add_chat_extracts_likes_into_social_db(tmp_path):
    rm, db = _rm_with_db(tmp_path)
    rm.add_chat("Emir", "user", "seviyorum satranc")
    profile = rm.social_profile("Emir")
    assert any("satranc" in str(x) for x in profile.get("likes", []))


def test_social_profile_includes_trust_score(tmp_path):
    rm, db = _rm_with_db(tmp_path)
    rec = db.persons.upsert(name="Emir", trust_score=0.7)
    profile = rm.social_profile("Emir")
    assert profile.get("trust_score") == 0.7 or profile.get("trust_score") is not None


def test_recall_candidates_include_moments(tmp_path):
    rm, db = _rm_with_db(tmp_path)
    rm.add_chat("Emir", "user", "seviyorum satranc")
    candidates = rm.recall_candidates("Emir")
    assert candidates


def test_json_fallback_extracts_preferences(tmp_path):
    path = tmp_path / "rel.json"
    rm = RelationshipMemory(enabled=True, path=str(path), social_db=None)
    rm.add_chat("Ali", "user", "seviyorum muzik")
    profile = rm.social_profile("Ali")
    assert any("muzik" in str(x) for x in profile.get("likes", []))

def test_relationship_memory_classifies_owner_and_guest():
    mem = RelationshipMemory(enabled=True, social_db=False)
    mem._social_db = None
    mem.observe_person("owner", is_owner=True)
    mem.observe_person("guest", is_owner=False)
    assert mem.classify_person("owner") == "owner"
    assert mem.classify_person("guest") == "known_guest"
    assert mem.classify_person("stranger") == "unknown_guest"
