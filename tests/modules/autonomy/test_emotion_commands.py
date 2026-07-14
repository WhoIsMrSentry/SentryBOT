"""Tests for spoken emotion imperative commands."""
from __future__ import annotations

from modules.autonomy.services.brain import AutonomyBrain


def test_sinirlen_maps_to_anger():
    assert AutonomyBrain._emotion_command_for_text("sinirlen") == "anger"


def test_short_phrase_mutlu_ol_maps_to_joy():
    assert AutonomyBrain._emotion_command_for_text("mutlu ol") == "joy"


def test_long_sentence_not_emotion_command():
    assert AutonomyBrain._emotion_command_for_text("lütfen sinirli ol") is None
    assert AutonomyBrain._emotion_command_for_text("bugun hava nasil") is None


def test_emotion_scene_name_aliases():
    assert AutonomyBrain._emotion_scene_name("sadness") == "emotion_sad"
    assert AutonomyBrain._emotion_scene_name("anger") == "emotion_angry"
    assert AutonomyBrain._emotion_scene_name("joy") == "emotion_joy"
