from __future__ import annotations

from dataclasses import dataclass

from modules.speak.xSpeakService import SpeakService


@dataclass
class _DummyPCM:
    samplerate: int = 22050


class _DummyTTS:
    def synthesize(self, text: str, overrides=None):
        return _DummyPCM()


class _DummyPlayer:
    def play_blocking(self, pcm):
        return 1.25


class _FakeSpeakService(SpeakService):
    def __init__(self):
        self.cfg = {"tts": {"engine": "dummy"}}
        self.tts = _DummyTTS()
        self.player = _DummyPlayer()
        self._liveliness_cfg = {
            "enabled": True,
            "interactions_base_url": "http://localhost:8080/interactions",
            "speech_effect": {
                "name": "PULSE",
                "tone_effect_map": {
                    "fast": "COMET",
                    "neutral": "PULSE",
                    "calm": "BREATHE",
                    "tired": "THEATER_CHASE",
                },
                "emphasis_effect_map": {
                    "exclamation": "COMET",
                    "question": "TWINKLE",
                },
                "rhythm": {
                    "enabled": True,
                    "mode": "clauses",
                    "effect": "PULSE",
                    "words_per_beat": 3,
                    "clauses_per_beat": 1,
                    "max_beats": 4,
                    "duration_ms": 150,
                    "max_pause_marks": 4,
                    "pause_effect_map": {
                        ",": "TWINKLE",
                        ".": "BREATHE",
                    },
                },
                "min_duration_ms": 400,
                "max_duration_ms": 7000,
                "chars_per_second": 16,
                "force": False,
            },
        }
        self.calls = []

    def _post_interactions(self, endpoint: str, payload: dict) -> None:
        self.calls.append((endpoint, payload))


def test_speak_emits_liveliness_start_and_end():
    svc = _FakeSpeakService()
    res = svc.speak("Merhaba dunya", tone={"rate": 170})
    assert res["ok"] is True
    assert svc.calls[0][0] == "/event"
    assert svc.calls[0][1]["type"] == "speech.start"
    assert svc.calls[0][1]["data"]["tone_key"] == "neutral"
    assert any(c[0] == "/effect" and c[1].get("name") == "PULSE" for c in svc.calls)
    assert svc.calls[-1][0] == "/event"
    assert svc.calls[-1][1]["type"] == "speech.end"


def test_estimated_effect_duration_is_clamped():
    svc = _FakeSpeakService()
    d1 = svc._estimate_effect_duration_ms("x", {"rate": 400})
    d2 = svc._estimate_effect_duration_ms("x" * 5000, {"rate": 80})
    assert d1 >= 400
    assert d2 <= 7000


def test_tone_effect_mapping_for_fast_tone():
    svc = _FakeSpeakService()
    svc.speak("Hizli cevap", tone={"rate": 210})
    assert svc.calls[0][1]["data"]["tone_key"] == "fast"
    assert svc.calls[1][1]["name"] == "COMET"


def test_emphasis_effects_are_emitted_for_punctuation():
    svc = _FakeSpeakService()
    svc.speak("Gercekten mi?!")
    effect_names = [c[1].get("name") for c in svc.calls if c[0] == "/effect"]
    assert "TWINKLE" in effect_names
    assert "COMET" in effect_names


def test_rhythm_beats_emit_multiple_pulse_effects():
    svc = _FakeSpeakService()
    svc.speak("Bir iki uc, dort bes alti, yedi sekiz dokuz.")
    rhythm_effects = [c for c in svc.calls if c[0] == "/effect" and c[1].get("name") == "PULSE" and c[1].get("duration_ms") == 150]
    assert len(rhythm_effects) >= 2


def test_pause_marks_emit_pause_effects():
    svc = _FakeSpeakService()
    svc.speak("Merhaba, nasilsin.")
    effect_names = [c[1].get("name") for c in svc.calls if c[0] == "/effect"]
    assert "TWINKLE" in effect_names
    assert "BREATHE" in effect_names
