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


def test_speak_accepts_string_tone_preset() -> None:
    svc = SpeakService.__new__(SpeakService)
    svc.cfg = {"tts": {"engine": "dummy"}}
    svc.tts = _DummyTTS()
    svc.player = _DummyPlayer()
    svc._liveliness_cfg = {}

    result = svc.speak("Merhaba", tone="calm")

    assert result["ok"] is True
    assert svc.tts.last_overrides is not None
    assert svc.tts.last_overrides.get("rate") == 170
    assert svc.tts.last_overrides.get("volume") == 0.7


def test_coerce_tone_rejects_invalid_type() -> None:
    assert SpeakService._coerce_tone({"rate": 180}) == {"rate": 180}
    assert SpeakService._coerce_tone("calm") == {"rate": 170, "volume": 0.7}
    assert SpeakService._coerce_tone(42) is None
