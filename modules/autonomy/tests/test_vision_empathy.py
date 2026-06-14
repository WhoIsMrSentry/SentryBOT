"""Tests for vision empathy mirroring."""
from __future__ import annotations

from unittest.mock import MagicMock

from modules.autonomy.services.brain_parts.vision import VisionMixin


class _Mini(VisionMixin):
    def __init__(self):
        self._vision_cfg = {
            "empathy": {
                "enabled": True,
                "cooldown_s": 0.0,
                "mirror": ["joy", "sadness"],
            }
        }
        self.state = {}
        self.client = MagicMock()
        self.express = MagicMock(return_value="joy")
        self._speak_with_mood = MagicMock()


def test_mirror_person_emotion_happy():
    mini = _Mini()
    mini._mirror_person_emotion({"name": "Ali", "emotion": "happy"})
    mini.express.assert_called_once_with("joy")
    mini.client.push_interaction_event.assert_called_with("vision.person_emotion_joy")


def test_mirror_skips_unknown_emotion():
    mini = _Mini()
    mini._mirror_person_emotion({"name": "Ali", "emotion": "disgust"})
    mini.express.assert_not_called()
