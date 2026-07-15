"""Smoke + behaviour tests for the canonical emotion vocabulary."""

from __future__ import annotations

import importlib


def test_import():
    module = importlib.import_module("modules.common.emotion_vocab")
    assert hasattr(module, "get_vocab")


def test_config_loader():
    from modules.common.emotion_vocab import load_vocab

    vocab = load_vocab()
    assert vocab.canonical_keys(), "expected at least one canonical emotion"
    assert "neutral" in vocab.canonical_keys()


def test_alias_resolution():
    from modules.common.emotion_vocab import get_vocab

    vocab = get_vocab()
    assert vocab.canonical("happy") == "joy"
    assert vocab.canonical("sad") == "sadness"
    assert vocab.canonical("sleepy") == "tired"
    assert vocab.canonical("angry") == "anger"
    assert vocab.canonical("scared") == "fear"
    # canonical labels resolve to themselves
    assert vocab.canonical("joy") == "joy"


def test_unknown_falls_back_to_default():
    from modules.common.emotion_vocab import get_vocab

    vocab = get_vocab()
    assert vocab.canonical(None) == "neutral"
    assert vocab.canonical("") == "neutral"
    assert vocab.canonical("definitely-not-an-emotion") == "neutral"


def test_render_hints_are_consistent():
    from modules.common.emotion_vocab import emotion_render

    render = emotion_render("happy")
    assert render.canonical == "joy"
    # the alias and the canonical must yield identical render hints
    assert emotion_render("joy") == render
    assert isinstance(render.rgb, tuple) and len(render.rgb) == 3
    assert render.oled and render.palette and render.effect and render.ears and render.tone


def test_service_init():
    # The vocab acts as the module's "service": construct it from defaults.
    from modules.common.emotion_vocab import EmotionVocab, load_vocab

    assert isinstance(load_vocab(), EmotionVocab)
