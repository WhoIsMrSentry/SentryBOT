from __future__ import annotations

from modules.autonomy.services.mood import MoodManager


def test_body_language_uses_configured_profile():
    cfg = {
        "defaults": {
            "mood": {"initial_happiness": 90, "initial_energy": 80, "decay_rate": 0.0},
            "body_language": {
                "profiles": {
                    "joy": {"pan_delta": 9, "tilt_delta": 4, "event": "autonomy.joy"}
                }
            },
        }
    }
    mood = MoodManager(cfg)
    profile = mood.get_body_language_profile()
    assert profile["pan_delta"] == 9
    assert profile["event"] == "autonomy.joy"


def test_body_language_fallback_profile_exists():
    mood = MoodManager({"defaults": {"mood": {"initial_happiness": 50, "initial_energy": 100, "decay_rate": 0.0}}})
    profile = mood.get_body_language_profile()
    assert "pan_delta" in profile
    assert "tilt_delta" in profile
