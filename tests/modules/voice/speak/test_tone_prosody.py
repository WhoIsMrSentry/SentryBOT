"""Emotion tone shapes Piper prosody (length_scale / noise_w)."""

from __future__ import annotations

from dataclasses import dataclass

from modules.voice.speak.xSpeakService import SpeakService


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


import threading

def _piper_service():
    svc = SpeakService.__new__(SpeakService)
    svc.cfg = {"tts": {"engine": "piper"}}
    svc.tts = _DummyTTS()
    svc.player = _DummyPlayer()
    svc._liveliness_cfg = {}
    # R21 split locks: synthesis and playback serialize independently.
    svc._synth_lock = threading.RLock()
    svc._play_lock = threading.Lock()
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


# voice_tone values emitted by modules/common/config/emotions.yml -- every one
# must resolve to a real prosody preset (never speak in a flat default voice).
_EMOTIONS_YML_TONES = [
    "neutral", "happy", "sad", "angry", "fear", "surprise", "excited",
    "gentle", "love", "disgusted", "confused", "worried", "bored",
    "tired", "curious", "calm", "proud", "embarrassed", "awe",
    "suspicious", "joy", "safety",
]


def test_every_emotions_yml_voice_tone_has_prosody_preset():
    from modules.voice.speak.xSpeakService import _TONE_PRESETS
    missing = [t for t in _EMOTIONS_YML_TONES if t not in _TONE_PRESETS]
    assert not missing, f"voice_tone presets missing: {missing}"
    for name, preset in _TONE_PRESETS.items():
        assert 90 <= preset.get("rate", 0) <= 260, f"{name}: rate out of range"
        assert 0.3 <= preset.get("volume", 0) <= 1.0, f"{name}: volume out of range"


def test_bored_speaks_slower_than_excited():
    svc = _piper_service()
    svc.speak("Ya", tone="bored")
    bored = svc.tts.last_overrides["piper"]["length_scale"]
    svc2 = _piper_service()
    svc2.speak("Ya", tone="excited")
    excited = svc2.tts.last_overrides["piper"]["length_scale"]
    assert bored > excited  # slower / lower energy
