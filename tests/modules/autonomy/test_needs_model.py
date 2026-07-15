"""Tests for config-driven need axes on MoodManager."""
from __future__ import annotations

from modules.autonomy.services.mood import MoodManager


def _cfg():
    return {
        "defaults": {
            "mood": {
                "needs": {
                    "social": {"initial": 60, "decay_per_s": 0.1, "interaction_fill": 20},
                    "stimulation": {"initial": 30, "growth_per_s": 0.2, "interaction_drain": 15},
                    "rest": {"initial": 70, "drain_per_s": 0.05},
                }
            }
        }
    }


def test_needs_initialized_from_config():
    mood = MoodManager(_cfg(), social_db=None)
    needs = mood.get_needs()
    assert needs["social"] == 60.0
    assert needs["stimulation"] == 30.0
    assert needs["rest"] == 70.0


def test_satisfy_need_lowers_social_and_stimulation():
    mood = MoodManager(_cfg(), social_db=None)
    mood.satisfy_need("social", 25)
    mood.satisfy_need("stimulation", 10)
    needs = mood.get_needs()
    assert needs["social"] == 35.0
    assert needs["stimulation"] == 20.0


def test_update_grows_stimulation_and_drains_rest():
    mood = MoodManager(_cfg(), social_db=None)
    mood.last_update -= 5.0
    mood.update()
    needs = mood.get_needs()
    assert needs["stimulation"] > 30.0
    assert needs["rest"] < 70.0
