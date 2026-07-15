"""Autonomy tone profiles resolve through the canonical emotion vocabulary."""

from __future__ import annotations

from modules.autonomy.services.brain_parts.vocal import VocalMixin


class _ToneBrain(VocalMixin):
    def __init__(self):
        self.state = {}

    class _Mood:
        def get_dominant_emotion(self):
            return "neutral"

    mood = _Mood()


def test_aliases_resolve_to_same_profile_as_canonical():
    brain = _ToneBrain()
    # "happy" is an alias of canonical "joy"
    assert brain._tone_profile("happy") == brain._tone_profile("joy")
    # "scared" -> fear, "angry" -> anger
    assert brain._tone_profile("scared") == brain._tone_profile("fear")
    assert brain._tone_profile("angry") == brain._tone_profile("anger")


def test_anger_is_faster_and_louder_than_sadness():
    brain = _ToneBrain()
    anger = brain._tone_profile("anger")
    sad = brain._tone_profile("sadness")
    assert anger["rate"] > sad["rate"]
    assert anger["volume"] >= sad["volume"]


def test_unknown_emotion_falls_back_to_neutral():
    brain = _ToneBrain()
    assert brain._tone_profile("zxcv") == {"rate": 170, "volume": 0.85}


def test_none_emotion_uses_dominant_mood():
    brain = _ToneBrain()
    assert brain._tone_profile(None)["rate"] == 170
