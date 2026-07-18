from __future__ import annotations

from modules.autonomy.services.world_memory import WorldMemory


def test_schema_lists_core_kinds():
    mem = WorldMemory({"persistence_enabled": False})
    schema = mem.schema()
    assert schema["ok"] is True
    assert {"people", "places", "objects", "events", "observations", "habits"}.issubset(set(schema["kinds"]))


def test_observe_person_merges_by_name():
    mem = WorldMemory({"persistence_enabled": False})
    first = mem.observe({"kind": "person", "name": "Emir", "confidence": 0.7}, source="test", now=1.0)
    second = mem.observe({"kind": "person", "name": "Emir", "confidence": 0.9, "properties": {"role": "owner"}}, source="test", now=2.0)
    assert first["created"] is True
    assert second["created"] is False
    assert second["item"]["kind"] == "people"
    assert second["item"]["count"] == 2
    assert second["item"]["confidence"] == 0.9
    assert second["item"]["properties"]["role"] == "owner"


def test_recent_filters_by_kind():
    mem = WorldMemory({"persistence_enabled": False})
    mem.observe({"kind": "object", "name": "red cube"}, now=1.0)
    mem.observe({"kind": "place", "name": "desk"}, now=2.0)
    recent = mem.recent(kind="objects", limit=5)
    assert recent["ok"] is True
    assert recent["count"] == 1
    assert recent["items"][0]["name"] == "red cube"


def test_observation_uses_summary_source_key():
    mem = WorldMemory({"persistence_enabled": False})
    a = mem.observe({"kind": "observation", "summary": "quiet room"}, source="vision", now=1.0)
    b = mem.observe({"kind": "observation", "summary": "quiet room"}, source="vision", now=2.0)
    assert a["created"] is True
    assert b["created"] is False
    assert b["item"]["count"] == 2


def test_clear_one_kind():
    mem = WorldMemory({"persistence_enabled": False})
    mem.observe({"kind": "object", "name": "ball"})
    mem.observe({"kind": "person", "name": "owner"})
    result = mem.clear(kind="objects")
    status = mem.status()
    assert result["removed"] == 1
    assert status["counts"]["objects"] == 0
    assert status["counts"]["people"] == 1
