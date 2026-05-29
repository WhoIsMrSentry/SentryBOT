"""Tests for the anger axis and the affective appraisal engine."""

from __future__ import annotations

from modules.autonomy.services.mood import MoodManager
from modules.autonomy.services.affective_appraisal import AffectiveAppraisal


def _mood():
    return MoodManager({"defaults": {"mood": {"initial_happiness": 50, "initial_energy": 100}}})


def test_anger_axis_exists_and_decays():
    mood = _mood()
    assert "anger" in mood.state
    mood.state["anger"] = 50
    mood.last_update -= 10  # simulate elapsed time
    mood.update()
    assert mood.state["anger"] < 50


def test_dominant_emotion_includes_anger_and_furious():
    mood = _mood()
    mood.state["anger"] = 50
    assert mood.get_dominant_emotion() == "anger"
    mood.state["anger"] = 90
    assert mood.get_dominant_emotion() == "furious"


def test_body_language_profile_for_anger():
    mood = _mood()
    mood.state["anger"] = 90
    profile = mood.get_body_language_profile()
    assert profile["event"] == "autonomy.angry"
    assert profile["pan_delta"] >= 9


def test_appraisal_applies_mood_deltas():
    mood = _mood()
    appraisal = AffectiveAppraisal()
    before = mood.state["anger"]
    matched = appraisal.apply(mood, "user_rude")
    assert matched == "user_rude"
    assert mood.state["anger"] > before
    assert mood.state["happiness"] < 50


def test_appraisal_intensity_scales_and_clamps():
    mood = _mood()
    appraisal = AffectiveAppraisal()
    appraisal.apply(mood, "user_insult", intensity=5.0)
    # mood.modify clamps to [0, 100]
    assert 0 <= mood.state["anger"] <= 100
    assert mood.state["anger"] == 100


def test_unknown_event_is_noop():
    mood = _mood()
    appraisal = AffectiveAppraisal()
    snapshot = dict(mood.state)
    assert appraisal.apply(mood, "not_a_real_event") is None
    assert mood.state == snapshot


def test_sentiment_keyword_mapping():
    from modules.autonomy.services.brain import AutonomyBrain

    assert AutonomyBrain._sentiment_event_for_text("seni cok seviyorum") == "user_praise"
    assert AutonomyBrain._sentiment_event_for_text("aptal robot") == "user_rude"
    assert AutonomyBrain._sentiment_event_for_text("bugun hava nasil") is None
