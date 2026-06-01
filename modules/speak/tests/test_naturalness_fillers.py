"""Natural-speech filler injection (disfluency)."""

from __future__ import annotations

import random

from modules.speak.xSpeakService import SpeakService


def _svc(cfg=None):
    svc = SpeakService.__new__(SpeakService)
    svc._naturalness_cfg = cfg if cfg is not None else {
        "enabled": True,
        "filler_probability": 0.5,
        "min_chars": 12,
        "fillers": {"default": ["Şey,", "Yani,", "Hmm,"]},
    }
    svc._rng = random.Random(0)
    return svc


def test_filler_is_prepended_when_roll_succeeds():
    svc = _svc()
    out = svc._enrich_text_for_speech("Bugün hava çok güzel görünüyor", rng=random.Random(1))
    # rng seeded so roll < probability -> a filler is added
    assert out.split()[0].rstrip(",").lower() in {"şey", "yani", "hmm"}


def test_short_text_is_left_alone():
    svc = _svc()
    assert svc._enrich_text_for_speech("Evet.") == "Evet."


def test_disabled_config_is_noop():
    svc = _svc({"enabled": False})
    assert svc._enrich_text_for_speech("Bugün hava çok güzel") == "Bugün hava çok güzel"


def test_does_not_stack_when_already_starting_with_filler():
    svc = _svc()
    # force probability 1.0
    svc._naturalness_cfg["filler_probability"] = 1.0
    text = "Hmm, bu konuyu biraz düşünmem lazım"
    assert svc._enrich_text_for_speech(text) == text


def test_high_probability_always_adds_filler():
    svc = _svc()
    svc._naturalness_cfg["filler_probability"] = 1.0
    out = svc._enrich_text_for_speech("Bu cümle yeterince uzun bir cümledir")
    assert out != "Bu cümle yeterince uzun bir cümledir"
    assert out.endswith("Bu cümle yeterince uzun bir cümledir")
