"""Emotion/tone-aware filler pool selection."""

from __future__ import annotations

import random

from modules.speak.xSpeakService import SpeakService


def _svc():
    svc = SpeakService.__new__(SpeakService)
    svc._naturalness_cfg = {
        "enabled": True,
        "filler_probability": 1.0,
        "min_chars": 5,
        "fillers": {
            "default": ["Şey,"],
            "joy": ["Aa,"],
            "sadness": ["Eh,"],
            "excitement": ["Vay,"],
        },
    }
    svc._rng = random.Random(0)
    return svc


def test_string_tone_selects_emotion_pool():
    svc = _svc()
    # "happy" -> canonical joy -> joy pool
    out = svc._enrich_text_for_speech("Bugün harika bir gün oldu", tone="happy")
    assert out.startswith("Aa,")


def test_fast_rate_dict_selects_excitement_pool():
    svc = _svc()
    out = svc._enrich_text_for_speech("Bunu hemen denemek istiyorum", tone={"rate": 200})
    assert out.startswith("Vay,")


def test_slow_rate_dict_selects_sadness_pool():
    svc = _svc()
    out = svc._enrich_text_for_speech("Biraz yorgun hissediyorum bugün", tone={"rate": 145})
    assert out.startswith("Eh,")


def test_unknown_tone_falls_back_to_default_pool():
    svc = _svc()
    out = svc._enrich_text_for_speech("Sıradan bir cümle kuruyorum", tone={"rate": 175})
    assert out.startswith("Şey,")


def test_pool_key_resolution_for_aliases():
    assert SpeakService._pool_key_for_tone("scared") == "fear"
    assert SpeakService._pool_key_for_tone({"rate": 210}) == "excitement"
    assert SpeakService._pool_key_for_tone(None) == "default"
