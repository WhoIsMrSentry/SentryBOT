from __future__ import annotations

import io
import subprocess
import sys
import threading
import wave
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from remote_tts import bootstrap as bootstrap_mod  # noqa: E402
from remote_tts import config as config_mod  # noqa: E402
from remote_tts import server as server_mod  # noqa: E402
from remote_tts import synth as synth_mod  # noqa: E402


def _make_runtime_cfg(tmp_path: Path, **overrides) -> config_mod.RuntimeConfig:
    defaults = dict(
        host="127.0.0.1",
        port=5000,
        auth_token="secret-token",
        tts_root=str(tmp_path / "runtime"),
        piper_root=str(tmp_path / "runtime" / "piper"),
        xtts_root=str(tmp_path / "runtime" / "xtts"),
        piper_bin="piper",
        xtts_bin="tts",
        bootstrap_on_start=False,
        ollama_tags_endpoint="http://127.0.0.1:11434/api/tags",
        ollama_chat_endpoint="http://127.0.0.1:11434/api/chat",
        max_upload_bytes=1024,
        synth_timeout_sec=5.0,
        wav_cache_max_entries=2,
    )
    defaults.update(overrides)
    return config_mod.RuntimeConfig(**defaults)


def _dummy_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 64)
    return buf.getvalue()


def test_load_runtime_config_handles_malformed_env_values(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_TTS_PORT", "not_a_port")
    monkeypatch.setenv("SENTRYBOT_TTS_MAX_UPLOAD_MB", "oops")
    monkeypatch.setenv("SENTRYBOT_TTS_CACHE_SIZE", "bad_int")
    monkeypatch.setenv("SENTRYBOT_TTS_SUBPROCESS_TIMEOUT", "bad_float")

    cfg = config_mod.load_runtime_config()
    assert cfg.port == 5000
    assert cfg.max_upload_bytes == 25 * 1024 * 1024
    assert cfg.wav_cache_max_entries == 32
    assert cfg.synth_timeout_sec == 60.0


def test_auth_upload_sanitization_and_size_limit(tmp_path: Path) -> None:
    app = server_mod.create_app(_make_runtime_cfg(tmp_path, max_upload_bytes=256))
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/tts/voices/piper").status_code == 401
        assert client.get("/ollama/tags").status_code == 401

        hdr = {"X-Auth-Token": "secret-token"}
        wav = _dummy_wav_bytes()

        # Path traversal and invalid filenames rejected with 400
        for bad_name in ("../evil.wav", "sub/evil.wav", "notes.txt"):
            resp = client.post(
                "/tts/voices/xtts/upload",
                headers=hdr,
                files={"file": (bad_name, wav, "audio/wav")},
            )
            assert resp.status_code == 400

        # Oversize upload rejected with 413
        oversize = client.post(
            "/tts/voices/xtts/upload",
            headers=hdr,
            files={"file": ("big.wav", b"A" * 512, "audio/wav")},
        )
        assert oversize.status_code == 413

        # Valid upload stored strictly under xtts_root
        ok = client.post(
            "/tts/voices/xtts/upload",
            headers=hdr,
            files={"file": ("ref_voice.wav", wav, "audio/wav")},
        )
        assert ok.status_code == 200
        assert (tmp_path / "runtime" / "xtts" / "ref_voice.wav").read_bytes() == wav
        assert list((tmp_path / "runtime" / "xtts").glob("*.tmp*")) == []


def test_ollama_tags_auth_and_nonblocking_lifespan_bootstrap(tmp_path: Path, monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def _slow_bootstrap(_cfg, force: bool = False):
        started.set()
        release.wait(timeout=1.0)
        return {"ok": True}

    monkeypatch.setattr(server_mod, "bootstrap_runtime", _slow_bootstrap)

    class _FakeResp:
        content = b'{"models":[{"name":"qwen"}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen"}]}

    monkeypatch.setattr(server_mod.requests, "get", lambda *_a, **_kw: _FakeResp())

    cfg = _make_runtime_cfg(tmp_path, bootstrap_on_start=True)
    app = server_mod.create_app(cfg)
    with TestClient(app) as client:
        assert started.wait(timeout=1.0)
        assert client.get("/ollama/tags").status_code == 401
        r = client.get("/ollama/tags", headers={"Authorization": "Bearer secret-token"})
        assert r.status_code == 200
        assert r.json()["payload"]["models"][0]["name"] == "qwen"
        release.set()


def test_synth_extra_args_timeout_lru_cache_and_streaming(tmp_path: Path, monkeypatch) -> None:
    # Allowlist & shell-injection rejection
    assert synth_mod._validate_xtts_extra_args(["--speed", "1.1", "--use_deepspeed"]) == [
        "--speed",
        "1.1",
        "--use_deepspeed",
    ]
    for bad in (["--bad_flag"], ["--speed", "1.0;rm"], ["positional"]):
        with pytest.raises(HTTPException) as exc:
            synth_mod._validate_xtts_extra_args(bad)
        assert exc.value.status_code == 400

    # Timeout -> HTTP 504
    fake_model = tmp_path / "runtime" / "piper" / "en_US-lessac-medium.onnx"
    fake_model.parent.mkdir(parents=True, exist_ok=True)
    fake_model.write_bytes(b"onnx")
    monkeypatch.setattr(synth_mod, "ensure_executable_exists", lambda b, _l: b)
    monkeypatch.setattr(synth_mod, "_try_inprocess_piper", lambda *_a, **_kw: None)

    def _timeout_run(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="piper", timeout=1.0)

    monkeypatch.setattr(synth_mod.subprocess, "run", _timeout_run)
    catalog = server_mod.VoiceCatalog(fake_model.parent, tmp_path / "xtts")
    catalog.refresh()
    with pytest.raises(HTTPException) as exc:
        synth_mod.run_piper_synthesis(
            text="hello",
            language="en",
            piper_opts={},
            catalog=catalog,
            default_piper_bin="piper",
            timeout_sec=1.0,
        )
    assert exc.value.status_code == 504

    # Feature L51: WavLRUCache + stream=True via FastAPI
    synth_calls = {"n": 0}
    wav_payload = _dummy_wav_bytes()

    def _fake_piper(**kwargs):
        synth_calls["n"] += 1
        return wav_payload

    monkeypatch.setattr(synth_mod, "run_piper_synthesis", _fake_piper)
    app = server_mod.create_app(_make_runtime_cfg(tmp_path, wav_cache_max_entries=2))
    hdr = {"X-Auth-Token": "secret-token"}
    with TestClient(app) as client:
        r1 = client.post("/tts/synthesize", headers=hdr, json={"text": "merhaba", "engine": "piper"})
        assert r1.status_code == 200
        assert r1.headers.get("X-Cache") == "miss"
        assert r1.content == wav_payload

        r2 = client.post(
            "/tts/synthesize",
            headers=hdr,
            json={"text": "merhaba", "engine": "piper", "stream": True},
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "hit"
        assert r2.content == wav_payload
        assert synth_calls["n"] == 1

        # LRU eviction check (capacity=2)
        client.post("/tts/synthesize", headers=hdr, json={"text": "iki", "engine": "piper"})
        client.post("/tts/synthesize", headers=hdr, json={"text": "uc", "engine": "piper"})
        assert client.get("/healthz").json()["cache"]["entries"] == 2


def test_bootstrap_atomic_download_and_offline_safety(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "model.onnx"
    dest.write_bytes(b"old-valid")

    class _FailingResp:
        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536):
            yield b"partial"
            raise RuntimeError("network drop")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(bootstrap_mod.requests, "get", lambda *_a, **_kw: _FailingResp())
    with pytest.raises(RuntimeError):
        bootstrap_mod.download_file("https://example.invalid/model.onnx", dest, timeout_sec=1.0)
    assert dest.read_bytes() == b"old-valid"
    assert list(tmp_path.glob("*.tmp.*")) == []

    monkeypatch.setattr(
        bootstrap_mod.requests,
        "get",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    cfg = _make_runtime_cfg(tmp_path, piper_models_source_url="https://example.invalid/models")
    summary = bootstrap_mod.bootstrap_piper_models(cfg, force=False)
    assert summary["offline_error"] == "offline"
    assert summary["available_models"] == 0
