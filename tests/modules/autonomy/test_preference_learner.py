"""PreferenceLearner: shared fact and preference extraction."""

from __future__ import annotations

from modules.autonomy.services.preference_learner import PreferenceLearner


def test_extracts_name_fact_turkish_and_english():
    pl = PreferenceLearner()
    assert "user name is Emir" in pl.extract_facts("benim adim Emir")
    assert "user name is Sarah" in pl.extract_facts("my name is Sarah")


def test_extracts_pet_and_location():
    pl = PreferenceLearner()
    assert "user has a pet named Max" in pl.extract_facts("my dog is Max")
    assert "user lives in Izmir" in pl.extract_facts("i live in Izmir")


def test_extracts_likes_and_dislikes():
    pl = PreferenceLearner()
    prefs = pl.extract_preferences("seviyorum kahve ama sevmiyorum spam")
    assert any("kahve" in x for x in prefs["likes"])
    assert any("spam" in x for x in prefs["dislikes"])


def test_extracts_topic_from_question():
    pl = PreferenceLearner()
    prefs = pl.extract_preferences("bugun hava nasil?")
    assert "hava" in prefs["topics"]


def test_user_only_strips_bot_side():
    pl = PreferenceLearner()
    facts = pl.extract_facts("User: benim adim Ali | Bot: selam")
    assert facts == ["user name is Ali"]
