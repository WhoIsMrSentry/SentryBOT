"""Tests for BehaviorComposer multi-modal execution and pose locking."""

import time
import pytest
from unittest.mock import MagicMock
from modules.autonomy.services.behavior_composer import BehaviorComposer


def test_behavior_composer_plan_execution():
    mock_brain = MagicMock()
    mock_client = MagicMock()
    composer = BehaviorComposer(brain=mock_brain, client=mock_client)

    plan = {
        "thought": "I want to rest in the quiet corner",
        "emotion": {"label": "gloomy", "intensity": 0.7, "duration_s": 20},
        "lights": {"palette_hint": "blue", "effect_hint": "breathe", "duration_s": 10},
        "vocal_sound": "confused",
        "say": {"text": "Dinlenmeye çekiliyorum.", "tone_hint": "calm"},
        "posture": {"head_tilt": 115, "eyes": "sleepy"},
        "look": {"pan": 135},
        "move": {"target": "right_back_corner"},
        "wake_when": {"person_enters": True},
        "duration_s": 30.0,
    }

    res = composer.execute_plan(plan)
    assert res["status"] == "executed"
    assert "thought" in res["components"]
    assert "emotion" in res["components"]
    assert "lights" in res["components"]
    assert "vocal_sound" in res["components"]
    assert "say" in res["components"]
    assert "head" in res["components"]

    # Verify calls
    mock_brain.memory.add_event.assert_called_with("I thought: I want to rest in the quiet corner")
    mock_client.express_emotion.assert_called_once_with(
        emotion="gloomy", intensity=0.7, duration=20.0, source="behavior_composer"
    )
    mock_client.set_neopixel.assert_called_once()
    mock_client.queue_action.assert_any_call("cute_sound", priority=65, payload={"sound": "confused", "mode": "play_emotion"})
    mock_brain._speak_with_mood.assert_called_once_with("Dinlenmeye çekiliyorum.", emotion="calm")
    mock_brain.execute_safe_rest_corner.assert_called_once()

    # Pose lock verification
    assert composer.is_pose_locked()


def test_behavior_composer_wake_condition():
    mock_brain = MagicMock()
    composer = BehaviorComposer(brain=mock_brain, client=MagicMock())

    plan = {
        "wake_when": {"person_enters": True},
        "duration_s": 10.0,
    }
    composer.execute_plan(plan)
    assert composer.is_pose_locked()

    # Non-matching event does not wake
    assert not composer.check_wake_condition("ambient_sound", {"volume": 0.2})
    assert composer.is_pose_locked()

    # Matching event wakes robot and releases lock
    assert composer.check_wake_condition("person_entered", {"count": 1})
    assert not composer.is_pose_locked()


def test_behavior_composer_macro_replay():
    mock_brain = MagicMock()
    mock_client = MagicMock()
    mock_shadow = MagicMock()
    mock_shadow.replay_macro.return_value = True
    mock_brain.shadow_learner = mock_shadow

    composer = BehaviorComposer(brain=mock_brain, client=mock_client)
    res = composer.execute_plan({"replay_macro": "greeting_sequence"})
    assert res["status"] == "executed"
    assert res["components"]["replay_macro"] == "greeting_sequence"
    mock_shadow.replay_macro.assert_called_once_with("greeting_sequence", mock_client)

