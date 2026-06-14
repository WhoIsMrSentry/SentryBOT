"""Tests for face conflict coordination."""
from __future__ import annotations

import time

from modules.oled_faces.services.face_coordinator import FaceCoordinator
from modules.oled_faces.services.mapper import FaceMapper, OledAction


def _coord(cfg=None):
    return FaceCoordinator(FaceMapper(cfg or {}), cfg or {"emotion_hold_s": 0.0, "session_hold_s": 10.0})


def test_emotion_event_uses_vocab_not_fallback():
    c = _coord()
    d = c.on_event("emotion:joy", OledAction("bitmap", "normal"), 65)
    assert d.apply is True
    assert d.action.name == "happy"


def test_speech_session_blocks_emotion_during_speaking():
    c = _coord()
    c.on_event("speech.start", OledAction("animation", "emotive"), 70)
    d = c.on_event("emotion:sad", OledAction("bitmap", "sad"), 65)
    assert d.apply is False


def test_speech_end_uses_baseline_not_forced_normal():
    c = _coord()
    baseline = OledAction("bitmap", "happy")
    d = c.on_event("speech.end", OledAction("bitmap", "normal"), 65, baseline=baseline)
    assert d.action.name == "happy"


def test_emotion_debounce_skips_rapid_flip():
    c = _coord({"emotion_hold_s": 5.0})
    first = c.on_event("emotion:joy", OledAction("bitmap", "happy"), 65)
    assert first.apply is True
    c.note_applied_mood("happy")
    second = c.on_event("emotion:sad", OledAction("bitmap", "sad"), 65)
    assert second.apply is False


def test_passive_operational_allows_emotion_poll():
    c = _coord({"emotion_hold_s": 0.0})
    d = c.from_state("idle", ["joy"], op_changed=False, emo_changed=True)
    assert d is not None
    assert d.apply is True
    assert d.action.name == "happy"
