"""Tests for conditional speech-side interaction events."""
from __future__ import annotations

from unittest.mock import MagicMock

from modules.autonomy.services.brain import AutonomyBrain


def _brain(cfg: dict | None = None) -> AutonomyBrain:
    config = {
        "llm": {"enabled": False},
        "speech_reactions": {
            "excited_on_speech": False,
            "excited_on_praise": True,
            "excited_on_questions": False,
        },
    }
    if cfg:
        config.update(cfg)
    brain = AutonomyBrain(config)
    brain.client = MagicMock()
    return brain


def test_no_excited_on_plain_speech():
    brain = _brain()
    brain._maybe_emit_speech_excited("bugun hava nasil", None)
    brain.client.push_interaction_event.assert_not_called()


def test_excited_on_praise():
    brain = _brain()
    brain._maybe_emit_speech_excited("aferin cok iyisin", "user_praise")
    brain.client.push_interaction_event.assert_called_once_with("autonomy.excited")


def test_excited_on_question_when_enabled():
    brain = _brain({"speech_reactions": {"excited_on_questions": True}})
    brain._maybe_emit_speech_excited("bu nedir?", None)
    brain.client.push_interaction_event.assert_called_once_with("autonomy.excited")
