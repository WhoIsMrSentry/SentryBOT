from __future__ import annotations

from dataclasses import dataclass

from modules.speak.services import tts as tts_mod


@dataclass
class _DummyPCM:
    samplerate: int = 22050
    channels: int = 1


class _FakeResponse:
    def __init__(self, content: bytes, headers: dict | None = None):
        self.content = content
        self.headers = headers or {"content-type": "audio/wav"}

    def raise_for_status(self) -> None:
        return None


def test_remote_tts_posts_single_endpoint_with_engine_for_piper(monkeypatch):
    captured: dict = {}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse(b"RIFF....WAVE")

    monkeypatch.setattr(tts_mod.requests, "post", _fake_post)
    monkeypatch.setattr(tts_mod, "_wav_bytes_to_pcm", lambda _: _DummyPCM())

    tts = tts_mod.TextToSpeech(
        {
            "engine": "piper",
            "language": "tr",
            "remote": {
                "enabled": True,
                "endpoint": "http://10.0.0.50:5000/tts/synthesize",
                "timeout": 15,
                "auth_token": "token-1",
            },
            "piper": {"speaker": 1},
            "xtts": {},
        }
    )

    out = tts.synthesize("merhaba")

    assert isinstance(out, _DummyPCM)
    assert captured["url"] == "http://10.0.0.50:5000/tts/synthesize"
    assert captured["json"]["engine"] == "piper"
    assert captured["json"]["text"] == "merhaba"
    assert captured["headers"]["Authorization"] == "Bearer token-1"


def test_remote_tts_override_switches_engine_to_xtts(monkeypatch):
    captured: dict = {}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(b"RIFF....WAVE")

    monkeypatch.setattr(tts_mod.requests, "post", _fake_post)
    monkeypatch.setattr(tts_mod, "_wav_bytes_to_pcm", lambda _: _DummyPCM())

    tts = tts_mod.TextToSpeech(
        {
            "engine": "piper",
            "language": "tr",
            "remote": {
                "enabled": True,
                "endpoint": "http://10.0.0.50:5000/tts/synthesize",
                "timeout": 15,
            },
            "piper": {},
            "xtts": {"speaker_wav": "/tmp/ref.wav"},
        }
    )

    out = tts.synthesize(
        "merhaba",
        overrides={
            "engine": "xtts",
            "language": "en",
            "speaker_wav": "/tmp/other.wav",
        },
    )

    assert isinstance(out, _DummyPCM)
    assert captured["json"]["engine"] == "xtts"
    assert captured["json"]["language"] == "en"
    assert captured["json"]["speaker_wav"] == "/tmp/other.wav"
