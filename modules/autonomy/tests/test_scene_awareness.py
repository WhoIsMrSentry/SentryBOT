"""Continuous scene awareness in the autonomy vision sense loop."""

from __future__ import annotations

from modules.autonomy.services.brain_parts.vision import VisionMixin


class _Mood:
    def __init__(self):
        self.mods = []

    def modify(self, axis, delta):
        self.mods.append((axis, delta))


class _Client:
    def __init__(self):
        self.events = []

    def push_interaction_event(self, event_type, data=None):
        self.events.append((event_type, data))


class _SceneBrain(VisionMixin):
    def __init__(self):
        self.client = _Client()
        self.mood = _Mood()
        self._vision_cfg = {"scene_novelty_threshold": 0.5}
        self.state = {}


def test_new_scene_emits_event_and_marks_unspoken():
    brain = _SceneBrain()
    brain._track_scene_context({"summary": "a person works at a wooden desk with a laptop"}, importance=0.6)

    assert brain.state["scene_summary"].startswith("a person")
    assert brain.state.get("scene_unspoken") is True
    events = {e for e, _ in brain.client.events}
    assert "environment.scene_changed" in events


def test_similar_scene_does_not_re_emit():
    brain = _SceneBrain()
    brain._track_scene_context({"summary": "a person at a desk with a laptop"}, importance=0.6)
    brain.client.events.clear()
    # nearly identical summary -> below novelty threshold -> no new event
    brain._track_scene_context({"summary": "a person at a desk with a laptop"}, importance=0.6)
    assert brain.client.events == []


def test_distinct_scene_re_emits():
    brain = _SceneBrain()
    brain._track_scene_context({"summary": "an empty hallway at night"}, importance=0.4)
    brain.client.events.clear()
    brain._track_scene_context({"summary": "two people cooking in a bright kitchen"}, importance=0.5)
    events = {e for e, _ in brain.client.events}
    assert "environment.scene_changed" in events


def test_empty_summary_is_ignored():
    brain = _SceneBrain()
    brain._track_scene_context({"summary": ""}, importance=0.9)
    assert brain.client.events == []
    assert "scene_summary" not in brain.state
