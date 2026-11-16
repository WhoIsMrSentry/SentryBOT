from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from modules.common.latency_trace import latency_trace
from modules.voice.speak.api.router import get_router
from modules.voice.speak.services import lang_detect
from modules.voice.speak.services import player as player_mod
from modules.voice.speak.services import tts as tts_mod
from modules.voice.speak.services import tts_remote_backends as remote_mod
from modules.voice.speak.services.pcm import PCM
from modules.voice.speak.xSpeakService import SpeakService


def test_audio_player_stop_playback_does_not_deadlock(monkeypatch) -> None:
    stopped = []

    class _FakeSD:
        @staticmethod
        def play(*_args, **_kwargs):
            return None

        @staticmethod
        def stop():
            stopped.append(True)

    monkeypatch.setattr(player_mod, "sd", _FakeSD)
    p = player_mod.AudioPlayer({"samplerate": 22050, "channels": 1})
    pcm = PCM(data=np.zeros(22050 * 2, dtype=np.float32), samplerate=22050, channels=1)

    t = threading.Thread(target=p.play_blocking, args=(pcm,), daemon=True)
    t.start()
    time.sleep(0.06)

    t0 = time.monotonic()
    p.stop_playback()
    t.join(timeout=1.0)
    elapsed = time.monotonic() - t0

    assert not t.is_alive()
    assert elapsed < 0.5
    assert stopped

    # Class-level call stops registered active players too
    p2 = player_mod.AudioPlayer({"samplerate": 22050, "channels": 1})
    player_mod.AudioPlayer.stop_playback()
    assert p2.is_stopped is True


def test_lang_detect_offline_and_preserves_explicit_on_ambiguous_text() -> None:
    assert not hasattr(lang_detect, "network_available")
    assert lang_detect.resolve_speak_language("12345 ???", explicit="tr", prefer_text=True) == "tr"
    assert lang_detect.resolve_speak_language("12345 ???", explicit="en", prefer_text=True) == "en"
    assert lang_detect.resolve_speak_language("Merhaba dünya bugün nasılsın?", explicit="en", prefer_text=True) == "tr"
    assert lang_detect.resolve_speak_language("This is an English answer.", explicit="tr", prefer_text=True) == "en"


def test_tts_caches_fallback_reraises_cancel_and_uses_lru_pcm_cache(monkeypatch, tmp_path: Path) -> None:
    tts_mod.clear_synthesis_cancel()
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    built_piper = []

    class _FakePiper(tts_mod.PiperBackend):
        def __init__(self, cfg, piper_cfg):
            self.tcfg = cfg
            self.piper_cfg = piper_cfg
            self.default_voice = "tr"
            built_piper.append(self)

        def synthesize(self, text: str, voice_key=None, runtime=None) -> PCM:
            return PCM(data=np.ones(64, dtype=np.float32), samplerate=22050, channels=1)

    monkeypatch.setattr(tts_mod, "PiperBackend", _FakePiper)

    calls = {"n": 0}

    def _remote_synth_ok(self, text: str, speaker_wav=None, language=None) -> PCM:
        calls["n"] += 1
        return PCM(data=np.full(128, float(calls["n"]), dtype=np.float32), samplerate=22050, channels=1)

    monkeypatch.setattr(tts_mod.RemoteTTSHttpBackend, "synthesize", _remote_synth_ok)

    tts = tts_mod.TextToSpeech(
        {
            "engine": "piper",
            "language": "tr",
            "remote": {"enabled": True, "endpoint": "http://127.0.0.1:5000/tts/synthesize", "timeout": 2},
            "piper": {},
            "xtts": {},
            "pcm_cache_max_entries": 2,
            "pcm_cache_max_chars": 20,
        }
    )

    p1 = tts.synthesize("selam")
    p2 = tts.synthesize("selam")
    assert calls["n"] == 1
    assert np.allclose(p1.data, p2.data)
    assert tts.health()["pcm_cache"]["hits"] == 1

    # Eviction beyond max_entries=2
    tts.synthesize("iki")
    tts.synthesize("uc")
    assert tts.health()["pcm_cache"]["entries"] == 2
    tts.synthesize("selam")
    assert calls["n"] == 4

    # Long text (> 20 chars) bypasses cache
    tts.synthesize("bu cok uzun bir test cumlesidir")
    tts.synthesize("bu cok uzun bir test cumlesidir")
    assert calls["n"] == 6

    # Cached local Piper fallback on remote error, EXCEPT synthesis_cancelled
    def _remote_fail(self, text: str, speaker_wav=None, language=None) -> PCM:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(tts_mod.RemoteTTSHttpBackend, "synthesize", _remote_fail)
    tts.synthesize("fallback bir")
    tts.synthesize("fallback iki")
    assert len(built_piper) == 1

    def _remote_cancel(self, text: str, speaker_wav=None, language=None) -> PCM:
        raise RuntimeError("synthesis_cancelled")

    monkeypatch.setattr(tts_mod.RemoteTTSHttpBackend, "synthesize", _remote_cancel)
    with pytest.raises(RuntimeError, match="synthesis_cancelled"):
        tts.synthesize("iptal")
    assert len(built_piper) == 1

    _ = tmp_path  # fixture available


def test_remote_backend_reuses_http_session(monkeypatch) -> None:
    posted = []

    class _FakeResp:
        status_code = 200
        content = b"RIFF"

        def raise_for_status(self):
            return None

    class _FakeSession:
        def post(self, url, json=None, headers=None, timeout=None):
            posted.append((url, json, headers, timeout))
            return _FakeResp()

    monkeypatch.setattr(remote_mod, "_HTTP_SESSION", _FakeSession())
    resp = remote_mod._http_post(
        __import__("requests"),
        "http://127.0.0.1:5000/tts/synthesize",
        json={"text": "hi"},
        headers={},
        timeout=3.0,
    )
    assert resp.content == b"RIFF"
    assert len(posted) == 1


def test_speak_service_gateway_url_unified_stop_and_stream_queue(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    monkeypatch.setenv("SENTRY_GATEWAY_URL", "http://127.0.0.1:9123")
    svc = SpeakService()
    resolved = svc._resolve_expression_url("@gateway/expression")
    assert resolved == "http://127.0.0.1:9123/expression"

    events = []
    svc.register_playback_listener(lambda active, rms: events.append((active, rms)))
    svc.player = type(
        "_StubPlayer",
        (),
        {
            "_play_stop": threading.Event(),
            "is_stopped": False,
            "stop_playback": lambda self: self._play_stop.set(),
            "play_blocking": lambda self, pcm: 0.05,
        },
    )()
    svc.tts = type(
        "_StubTTS",
        (),
        {
            "synthesize": lambda self, text, overrides=None: PCM(
                data=np.zeros(128, dtype=np.float32), samplerate=22050, channels=1
            ),
            "health": lambda self: {"available": True, "engine": "dummy"},
        },
    )()

    res_stop = svc.stop_speaking()
    assert res_stop == {"ok": True, "stopped": True}
    assert events[-1] == (False, 0.0)
    svc.player._play_stop.clear()

    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    trace_id = "streamtrace001"
    resp = client.post(
        "/speak/say_stream",
        json={"text": "Birinci cumle burada. Ikinci cumle de burada.", "max_chunk_chars": 40, "trace_id": trace_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["chunks"] == 2
    job_id = body["job_id"]

    deadline = time.monotonic() + 2.0
    job = None
    while time.monotonic() < deadline:
        job = client.get(f"/speak/jobs/{job_id}").json()["job"]
        if job and job["status"] == "done":
            break
        time.sleep(0.02)

    assert job is not None and job["status"] == "done"
    assert job["done_chunks"] == 2
    parent = latency_trace.get(trace_id)
    assert parent is not None and parent["status"] == "done"
