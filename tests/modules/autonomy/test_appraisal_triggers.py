"""Tests for speech -> appraisal event mapping."""
from __future__ import annotations

from modules.autonomy.services.appraisal_triggers import speech_appraisal_event


def test_thanks_maps_to_user_thanks():
    assert speech_appraisal_event("çok teşekkür ederim") == "user_thanks"


def test_petted_keywords():
    assert speech_appraisal_event("seni okşadım") == "petted"


def test_played_with_keywords():
    assert speech_appraisal_event("benimle oyna") == "played_with"


def test_insult_before_rude():
    assert speech_appraisal_event("aptal gerizekalı") == "user_insult"


def test_neutral_question_returns_none():
    assert speech_appraisal_event("bugün hava nasıl") is None
