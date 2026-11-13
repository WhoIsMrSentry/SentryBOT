from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.voice.audio_router import (
    AudioCapture,
    AudioConfig,
    load_audio_router_config,
)
from modules.voice.speech.config_loader import load_audio_router_config as speech_load_router_cfg
from modules.voice.wakeword.api.router import get_router as get_wakeword_router
from modules.voice.wakeword.config_loader import (
    load_audio_router_config as wakeword_load_router_cfg,
    load_config as wakeword_load_config,
)
from modules.voice.wakeword.services import openwakeword_assets
from modules.voice.wakeword.services.wakeword_actions import WakewordActions
from modules.voice.wakeword.xWakewordService import WakewordService


def test_audio_router_rt_callback_enqueues_without_consumer_locks() -> None:
    cap = AudioCapture(AudioConfig(device="default", sample_rate=16000, channels=2, frame_size=256))
    seen: list[tuple[tuple[int, ...], float]] = []
    done = threading.Event()

    class _Consumer:
        def on_start(self) -> None:
            pass

        def on_stop(self) -> None:
            pass

        def on_audio_frame(self, frame: np.ndarray, ts: float) -> None:
            seen.append((frame.shape, ts))
            done.set()

    cap.register_consumer("c1", _Consumer())
    cap._running = True

    # Hold BOTH _consumers_lock and _vad._lock on this thread while simulating PortAudio callback
    pcm = np.full((256, 2), 1000, dtype=np.int16)
    with cap._consumers_lock:
        with cap._vad._lock:
            _raw, code = cap._audio_callback(pcm.tobytes(), 256, None, 0)
            assert code == 0

    # Now start dispatch worker and ensure buffered frame reaches consumer
    worker = threading.Thread(target=cap._dispatch_loop, daemon=True)
    worker.start()
    try:
        assert done.wait(timeout=1.0)
        assert seen[0][0] == (256, 2)
    finally:
        cap._running = False
        cap._stop_event.set()
        cap._raw_queue.put_nowait(None)
        worker.join(timeout=1.0)


def test_audio_router_find_device_parses_alsa_card_hint() -> None:
    cap = AudioCapture(AudioConfig(device="plughw:2,0", channels=2))
    devices = [
        {"name": "Built-in HDMI (hw:0,0)", "maxInputChannels": 2},
        {"name": "USB Array Mic (hw:2,0)", "maxInputChannels": 2},
    ]
    cap._pyaudio = SimpleNamespace(
        get_device_count=lambda: len(devices),
        get_device_info_by_index=lambda idx: devices[idx],
        get_default_input_device_info=lambda: {"index": 0},
    )
    assert cap._find_device() == 1


def test_audio_router_load_config_unified_samplerate() -> None:
    root = {
        "audio_router": {
            "capture": {
                "device": "hw:1,0",
                "samplerate": 16000,
                "channels": 2,
                "vad_threshold": 0.04,
            }
        }
    }
    cfg = load_audio_router_config(root)
    assert cfg.capture.sample_rate == 16000
    assert cfg.capture.device == "hw:1,0"
    assert cfg.capture.vad_threshold == pytest.approx(0.04)
    assert wakeword_load_router_cfg is load_audio_router_config
    assert speech_load_router_cfg is load_audio_router_config


def test_wakeword_retry_unlocks_listening_and_cancels_on_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = WakewordService.__new__(WakewordService)
    svc.cfg = {"wakeword": {"words": ["hey mycroft"]}, "actions": {}}
    svc._stop_event = threading.Event()
    svc._listening = False
    svc._lock = threading.Lock()
    svc._last_trigger_ts = 0.0
    svc._active_window = False
    svc._thread = None
    svc._stream_iter = None
    svc._degraded_reason = None
    svc._restart_attempts = 0
    svc._vad_gate_enabled = False
    svc._vad_min_rms = 0.0
    svc._vad_hangover_sec = 0.0
    svc._vad_hangover_until = 0.0
    svc._energy_gate_skipped = 0
    svc._energy_gate_passed = 0

    calls = 0
    recovered = threading.Event()

    class _FakeCapture:
        _vad = None

        def stream(self, stop_event=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("transient capture failure")
            recovered.set()
            while stop_event is not None and not stop_event.is_set():
                time.sleep(0.01)
            return iter(())

    svc._audio_router = SimpleNamespace(get_capture=lambda: _FakeCapture())
    svc._openwakeword = SimpleNamespace(_calibration_done=True, run=lambda _s: iter(()))

    # Avoid real 0.5s backoff sleep in unit test
    orig_wait = svc._stop_event.wait
    monkeypatch.setattr(svc._stop_event, "wait", lambda _t=None: orig_wait(0.01))

    svc.start()
    try:
        assert recovered.wait(timeout=1.0)
        assert calls >= 2
    finally:
        svc.stop()
        assert svc.listening is False


def test_wakeword_energy_gate_skips_silent_chunks() -> None:
    svc = WakewordService.__new__(WakewordService)
    svc._vad_gate_enabled = True
    svc._vad_min_rms = 40.0
    svc._vad_hangover_sec = 0.05
    svc._vad_hangover_until = 0.0
    svc._energy_gate_skipped = 0
    svc._energy_gate_passed = 0
    svc._openwakeword = SimpleNamespace(_calibration_done=True)

    silent = np.zeros(320, dtype=np.int16).tobytes()
    loud = np.full(320, 600, dtype=np.int16).tobytes()

    assert svc._should_feed_wakeword(silent, None) is False
    assert svc._energy_gate_skipped == 1
    assert svc._should_feed_wakeword(loud, None) is True
    assert svc._energy_gate_passed == 1
    # Hangover passes immediately after loud frame
    assert svc._should_feed_wakeword(silent, None) is True


def test_wakeword_actions_has_final_speech_dict_and_reuses_session(monkeypatch: pytest.MonkeyPatch) -> None:
    actions = WakewordActions({"stop_on_final": True, "speech_last_url": "http://127.0.0.1:8080/speech/last"})
    assert not hasattr(actions, "_neopixel_post")

    actions._speech_service = SimpleNamespace(
        last_result={"text": "hey mycroft saati söyle", "final": True, "ts": 200.0}
    )
    assert actions.has_final_speech(since_ts=150.0, wakeword="hey mycroft") is True

    # Wakeword-only utterance should NOT close command window early
    actions._speech_service.last_result = {"text": "hey mycroft", "final": True, "ts": 200.0}
    assert actions.has_final_speech(since_ts=150.0, wakeword="hey mycroft") is False

    # HTTP fallback reads JSON cleanly via persistent session
    actions._speech_service = None
    sess_calls: list[str] = []

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"text": "bugün hava nasıl", "final": True, "ts": 300.0}

    fake_sess = SimpleNamespace(
        get=lambda url, timeout=0.2: sess_calls.append(url) or _FakeResp(),
        post=lambda url, json=None, timeout=0.2: None,
    )
    monkeypatch.setattr("modules.voice.wakeword.services.wakeword_actions._http_session", lambda: fake_sess)
    assert actions.has_final_speech(since_ts=100.0) is True
    assert len(sess_calls) == 1


def test_wakeword_healthz_assets_and_config_loader(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_svc = SimpleNamespace(
        listening=False,
        status=lambda: {"ok": False, "listening": False, "degraded": True, "degraded_reason": "no_model"},
        start_background=lambda: None,
        stop=lambda: None,
    )
    app = FastAPI()
    app.include_router(get_wakeword_router(fake_svc))
    client = TestClient(app)
    hz = client.get("/wakeword/healthz")
    assert hz.status_code == 200
    assert hz.json()["ok"] is False
    assert hz.json()["degraded_reason"] == "no_model"

    # SENTRYBOT_NO_HARDWARE=1 must return None cleanly (not a truthy dict)
    monkeypatch.setenv("SENTRYBOT_NO_HARDWARE", "1")
    assert openwakeword_assets._ensure_openwakeword_assets(["hey_mycroft"], True) is None

    # Atomic download with timeout
    monkeypatch.delenv("SENTRYBOT_NO_HARDWARE", raising=False)
    dest = tmp_path / "model.onnx"

    class _StreamResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536):
            yield b"x" * 2048

    get_mock = MagicMock(return_value=_StreamResp())
    monkeypatch.setattr("requests.get", get_mock)
    openwakeword_assets._download_url("https://example/model.onnx", dest, timeout_s=15.0)
    assert dest.exists() and dest.stat().st_size == 2048
    assert not (tmp_path / f"model.onnx.tmp.{os.getpid()}").exists()
    assert get_mock.call_args.kwargs["timeout"] == 15.0

    # agent.yaml read error must not trigger UnboundLocalError
    monkeypatch.setattr(
        "modules.voice.wakeword.config_loader.load_agent_config",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("yaml broken")),
    )
    loaded = wakeword_load_config()
    assert "server" in loaded and "host" in loaded["server"]
