"""WorldState continuous environment perception fields."""

from __future__ import annotations

from modules.agent_core.services.world_state import WorldState


def test_update_scene_accepts_cache_envelope():
    ws = WorldState()
    ws.update_scene(
        {
            "available": True,
            "context": {
                "summary": "a person sits at a desk with a laptop",
                "objects": [{"label": "laptop"}, {"label": "cup"}],
                "hazards": [],
                "people": [{"name": "Emir", "recognition_level": 6}, {"name": "Unknown"}],
                "importance_score": 0.55,
                "timestamp": "2026-05-31T10:00:00",
            },
        }
    )
    env = ws.environment
    assert "laptop" in env["objects"]
    assert env["people_present"] == ["Emir"]  # Unknown filtered out
    assert env["importance"] == 0.55
    assert "desk" in env["scene_summary"]


def test_update_scene_accepts_raw_context():
    ws = WorldState()
    ws.update_scene({"summary": "empty hallway", "objects": [], "people": [], "hazards": []})
    assert ws.environment["scene_summary"] == "empty hallway"


def test_inject_world_state_includes_environment_when_present():
    ws = WorldState()
    ws.update_scene({"summary": "kitchen with a kettle", "objects": [{"label": "kettle"}], "people": []})
    injected = ws.inject_world_state("hello")
    assert "environment" in injected
    assert "kettle" in injected


def test_inject_world_state_omits_environment_when_idle():
    ws = WorldState()
    injected = ws.inject_world_state("hello")
    assert "environment" not in injected
