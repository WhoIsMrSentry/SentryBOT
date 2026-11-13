from __future__ import annotations

import math
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from modules.voice.speaker_id import config_loader
from modules.voice.speaker_id.api.router import get_router
from modules.voice.speaker_id.services import identity_fusion
from modules.voice.speaker_id.services.voiceprint import (
    VoiceprintEmbedder,
    f32_to_pcm_b64,
    pcm_b64_to_f32,
    to_mono_f32,
)
from modules.voice.speaker_id.services.voiceprint_store import VoiceprintStore
from modules.voice.speaker_id.xSpeakerIdService import SpeakerIdError, SpeakerIdService


def _synth_voice(freq: float, duration_s: float = 1.2, sr: int = 16000, amp: float = 0.35) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False, dtype=np.float32)
    sig = amp * (0.65 * np.sin(2.0 * math.pi * freq * t) + 0.35 * np.sin(2.0 * math.pi * (2.0 * freq) * t))
    return sig.astype(np.float32)


def test_embedder_native_16khz_fft_and_pitch() -> None:
    emb = VoiceprintEmbedder(bands=20, sample_rate=16000)
    assert emb.analysis_sr == 16000
    assert emb.window == 400
    assert emb.hop == 160
    assert emb.n_fft == 512

    tone = _synth_voice(150.0, duration_s=0.6, sr=16000)
    vec = emb.embed(tone, 16000, min_frames=10)
    assert vec is not None
    assert len(vec) == 43  # 20 means + 20 stds + f0_med + f0_spread + zcr

    frame = tone[: emb.window] * np.hanning(emb.window).astype(np.float32)
    f0 = emb._pitch(frame)
    assert 135.0 <= f0 <= 165.0


def test_pcm_b64_and_bytes_decoding() -> None:
    sig = _synth_voice(180.0, duration_s=0.2, sr=16000, amp=0.5)
    b64 = f32_to_pcm_b64(sig)
    decoded = pcm_b64_to_f32(b64)
    assert decoded.dtype == np.float32
    assert len(decoded) == len(sig)
    assert np.allclose(decoded, sig, atol=2e-4)

    int16_bytes = (np.clip(sig, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    mono = to_mono_f32(int16_bytes)
    assert len(mono) == len(sig)

    for bad in ("", "!!!not-base64!!!", "AA=="):  # "AA==" -> 1 byte (not int16 aligned)
        with pytest.raises(ValueError):
            pcm_b64_to_f32(bad)


def test_store_dimension_mismatch_and_ema_update(tmp_path: Path) -> None:
    store_file = tmp_path / "profiles.json"
    store = VoiceprintStore(str(store_file), max_profiles=4)
    store.upsert("ali", [1.0, 0.0, 0.0], replace=True)

    # Dimension change resets cleanly instead of raising numpy ValueError
    res = store.upsert("ali", [0.0, 1.0, 0.0, 0.0], replace=False)
    assert res["ok"] is True
    assert res["samples"] == 1
    assert len(store.all()["ali"]["vec"]) == 4

    assert store.update_ema("ali", [0.6, 0.8, 0.0, 0.0], alpha=0.1) is True
    assert store.all()["ali"]["n"] == 2
    assert store.update_ema("missing", [1.0, 0.0, 0.0, 0.0]) is False
    assert store.update_ema("ali", [1.0, 0.0]) is False

    reloaded = VoiceprintStore(str(store_file), max_profiles=4)
    assert reloaded.names() == ["ali"]


def test_identity_fusion_uses_monotonic_ttl(monkeypatch) -> None:
    now = {"t": 100.0}
    monkeypatch.setattr(identity_fusion.time, "monotonic", lambda: now["t"])
    resolver = identity_fusion.ActiveSpeakerResolver()
    resolver.observe_face("zeynep", confidence=0.9, ttl_s=5.0)
    assert resolver.resolve()["person_id"] == "zeynep"

    now["t"] = 104.0
    assert resolver.resolve()["person_id"] == "zeynep"

    now["t"] = 106.0
    assert resolver.resolve()["person_id"] is None


def test_config_loader_merges_agent_yaml_and_resolves_store_path(monkeypatch) -> None:
    monkeypatch.setenv("SPEAKER_ID_HOST", "127.0.0.1")
    cfg = config_loader.load_config(overrides={"max_profiles": 9})
    assert cfg["max_profiles"] == 9
    assert Path(cfg["store_path"]).is_absolute()
    assert cfg["server"]["host"] == "127.0.0.1"


def test_service_enroll_min_and_ema_snr_gate(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "cfg.yml"
    cfg_path.write_text(
        f"""
enabled: true
sample_rate: 16000
enroll_min_frames: 30
identify_min_frames: 3
store_path: "{(tmp_path / 'spk.json').as_posix()}"
threshold:
  similarity: 0.70
  margin: 0.05
ema_update:
  enabled: true
  alpha: 0.1
  min_similarity: 0.80
  min_margin: 0.05
  min_snr_db: 12.0
""",
        encoding="utf-8",
    )
    svc = SpeakerIdService(str(cfg_path))
    too_short = _synth_voice(145.0, duration_s=0.12, sr=16000)
    with pytest.raises(SpeakerIdError):
        svc.enroll_speaker("kaan", too_short, 16000)

    clean = _synth_voice(145.0, duration_s=1.2, sr=16000, amp=0.4)
    # Create natural silence+speech envelope so 90th vs 15th percentile has strong SNR
    clean[:4000] *= 0.002
    assert svc.enroll_speaker("kaan", clean, 16000)["samples"] == 1

    res_hi = svc.identify(clean, 16000)
    assert res_hi["known"] is True
    assert res_hi["name"] == "kaan"
    assert res_hi["snr_db"] >= 12.0
    assert res_hi["ema_updated"] is True
    assert svc.store.all()["kaan"]["n"] == 2

    # Low SNR (< 12 dB) must still identify without polluting EMA
    monkeypatch.setattr(svc.embedder, "estimate_snr_db", lambda _pcm, _sr: 4.5)
    res_lo = svc.identify(clean, 16000)
    assert res_lo["known"] is True
    assert res_lo["snr_db"] == 4.5
    assert res_lo["ema_updated"] is False
    assert svc.store.all()["kaan"]["n"] == 2


def test_router_pcm_b64_and_validation(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yml"
    cfg_path.write_text(
        f'enabled: true\nsample_rate: 16000\nstore_path: "{(tmp_path / "spk.json").as_posix()}"\n',
        encoding="utf-8",
    )
    svc = SpeakerIdService(str(cfg_path))
    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    voice = _synth_voice(160.0, duration_s=1.1, sr=16000, amp=0.4)
    r_en = client.post(
        "/speaker_id/enroll",
        json={"name": "elif", "pcm_b64": f32_to_pcm_b64(voice), "samplerate": 16000},
    )
    assert r_en.status_code == 200
    assert r_en.json()["ok"] is True

    r_id = client.post(
        "/speaker_id/identify",
        json={"pcm_b64": f32_to_pcm_b64(voice), "samplerate": 16000},
    )
    assert r_id.status_code == 200
    assert r_id.json()["known"] is True
    assert r_id.json()["name"] == "elif"

    # Invalid base64 -> 400; missing audio -> 400; out-of-range field -> 422
    assert client.post("/speaker_id/identify", json={"pcm_b64": "%%%"}).status_code == 400
    assert client.post("/speaker_id/identify", json={}).status_code == 400
    assert client.post("/speaker_id/signal", json={"modality": "face", "person_id": "elif", "confidence": 2.5}).status_code == 422

    assert client.post("/speaker_id/signal", json={"modality": "face", "person_id": "elif", "confidence": 0.9}).status_code == 200
    assert client.get("/speaker_id/active_identity").json()["person_id"] == "elif"
    assert client.get("/speaker_id/profiles").json()["profiles"] == ["elif"]
    assert client.delete("/speaker_id/forget/elif").json()["ok"] is True
    assert client.get("/speaker_id/profiles").json()["count"] == 0
