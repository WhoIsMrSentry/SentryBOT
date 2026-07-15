"""Emotion tone shapes Piper prosody (length_scale / noise_w)."""

from __future__ import annotations

from dataclasses import dataclass

from modules.speak.xSpeakService import SpeakService


@dataclass
class _DummyPCM:
    samplerate: int = 22050


class _DummyTTS:
    last_overrides: dict | None = None

    def synthesize(self, text: str, overrides=None):
        self.last_overrides = overrides
        return _DummyPCM()


class _DummyPlayer:
    def play_blocking(self, pcm):
        return 0.5


def _piper_service():
    svc = SpeakService.__new__(SpeakService)
    svc.cfg = {"tts": {"engine": "piper"}}
    svc.tts = _DummyTTS()
    svc.player = _DummyPlayer()
    svc._liveliness_cfg = {}
    return svc


def test_tone_to_piper_maps_rate_to_length_scale():
    fast = SpeakService._tone_to_piper({"rate": 200})
    slow = SpeakService._tone_to_piper({"rate": 140})
    # Faster speech -> shorter (smaller) length_scale than slower speech.
    assert fast["length_scale"] < slow["length_scale"]
    assert SpeakService._tone_to_piper(None) is None
    assert SpeakService._tone_to_piper({"volume": 0.5}) is None


def test_piper_engine_injects_prosody_overrides():
    svc = _piper_service()
    svc.speak("Merhaba", tone="excited")  # excited -> rate 200
    ov = svc.tts.last_overrides
    assert ov is not None and "piper" in ov
    assert "length_scale" in ov["piper"]
    assert ov["piper"]["length_scale"] < 1.0  # faster than baseline


def test_non_piper_engine_does_not_inject_piper_block():
    svc = _piper_service()
    svc.cfg = {"tts": {"engine": "dummy"}}
    svc.speak("Merhaba", tone="excited")
    assert "piper" not in (svc.tts.last_overrides or {})
