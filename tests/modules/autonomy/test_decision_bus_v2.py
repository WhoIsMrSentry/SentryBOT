"""Tests for Decision Bus v2 integration and speak tone presets."""

import pytest
from unittest.mock import MagicMock, patch
from modules.voice.speak.xSpeakService import _TONE_PRESETS
from modules.autonomy.services.brain import AutonomyBrain
from modules.autonomy.services.scene_register import SceneRegister
from modules.autonomy.services.behavior_composer import BehaviorComposer


def test_speak_tone_presets_expanded():
    assert "anger" in _TONE_PRESETS
    assert "angry" in _TONE_PRESETS
    assert "frustrated" in _TONE_PRESETS
    assert "frustration" in _TONE_PRESETS
    assert _TONE_PRESETS["anger"]["rate"] == 210
    assert _TONE_PRESETS["frustrated"]["volume"] == 0.9


def test_brain_initializes_scene_register_and_behavior_composer():
    cfg = {
        "endpoints": {},
        "defaults": {"boredom_threshold_s": 20},
        "scene_register": {"window_s": 4.0},
    }
    brain = AutonomyBrain(cfg)
    assert hasattr(brain, "scene_register")
    assert isinstance(brain.scene_register, SceneRegister)
    assert brain.scene_register.window_s == 4.0

    assert hasattr(brain, "behavior_composer")
    assert isinstance(brain.behavior_composer, BehaviorComposer)


def test_decision_bus_v2_prompt_injection_and_plan_handling():
    cfg = {
        "endpoints": {},
        "defaults": {"boredom_threshold_s": 20},
        "llm": {"enabled": True},
        "agentic": {"enabled": True},
    }
    brain = AutonomyBrain(cfg)
    brain.scene_register.update_person("owner_bob", region="center", distance_m=1.2)
    brain.scene_register.update_motion_energy({"top_left": 0.9})

    mock_agent = MagicMock()
    mock_agent.step.return_value = {
        "text": "Odayı gözlemledim.",
        "plan": {
            "thought": "I will rest now",
            "vocal_sound": "confused",
            "emotion": "gloomy",
            "wake_when": {"person_enters": True},
        }
    }
    brain.agent = mock_agent

    with patch.object(brain.behavior_composer, "execute_plan") as mock_exec:
        brain._make_agentic_decision(reason="boredom")

        # Verify prompt received scene context
        assert mock_agent.step.called
        sent_prompt = mock_agent.step.call_args[0][0]
        assert "Environment (Peripheral Vision):" in sent_prompt
        assert "owner_bob" in sent_prompt

        # Verify behavior composer executed plan
        mock_exec.assert_called_once()
        executed_plan = mock_exec.call_args[0][0]
        assert executed_plan["thought"] == "I will rest now"
        assert executed_plan["vocal_sound"] == "confused"
