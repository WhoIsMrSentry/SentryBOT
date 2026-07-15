"""Proactive ambient scene narration."""

from __future__ import annotations

from modules.autonomy.services.proactive_planner import ProactivePlanner


def _planner():
    return ProactivePlanner({"cooldown_s": 0.0, "min_idle_s": 0.0, "max_per_hour": 100})


def test_unspoken_important_scene_is_narrated_first():
    p = _planner()
    plan = p.propose(
        now_ts=1000.0,
        idle_s=60.0,
        dominant_emotion="neutral",
        last_speaker="",
        owner_present=False,
        scene={"summary": "two people are cooking in a bright kitchen", "importance": 0.6, "unspoken": True},
    )
    assert plan is not None
    assert plan["event"] == "companion.scene_comment"
    assert plan.get("scene_consumed") is True
    assert "kitchen" in plan["text"].lower()


def test_low_importance_scene_is_not_narrated():
    p = _planner()
    plan = p.propose(
        now_ts=1000.0,
        idle_s=60.0,
        dominant_emotion="neutral",
        last_speaker="",
        owner_present=False,
        scene={"summary": "a plain wall", "importance": 0.1, "unspoken": True},
    )
    # falls back to a normal proactive line, not a scene comment
    assert plan is not None
    assert plan["event"] == "companion.proactive"


def test_already_spoken_scene_is_skipped():
    p = _planner()
    plan = p.propose(
        now_ts=1000.0,
        idle_s=60.0,
        dominant_emotion="neutral",
        last_speaker="",
        owner_present=False,
        scene={"summary": "two people cooking in a kitchen", "importance": 0.8, "unspoken": False},
    )
    assert plan is not None
    assert plan["event"] == "companion.proactive"
