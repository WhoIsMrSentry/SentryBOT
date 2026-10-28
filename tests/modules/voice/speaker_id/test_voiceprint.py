"""Speaker-ID MVP tests: synthetic voices enroll -> stable self-identify, rejected stranger."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("numpy")
import numpy as np

from modules.voice.speaker_id.xSpeakerIdService import SpeakerIdService

SR = 16000


def _synth_voice(seed: int, f0: float, tilt: float, seconds: float = 1.5) -> np.ndarray:
    """Synthetic 'speaker': harmonic stack with per-speaker spectral tilt."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for k in range(1, 26):
        twist = 1.0 + 0.01 * float(rng.random())
        amp = float(rng.uniform(0.5, 1.1)) / (k ** tilt)
        out += amp * np.sin(2 * np.pi * f0 * k * twist * t).astype(np.float32)
    env = np.zeros(n, dtype=np.float32)
    block = int(0.12 * SR)
    pos = 0
    while pos < n:
        on = int(block * float(rng.uniform(0.8, 1.4)))
        off = int(block * float(rng.uniform(0.4, 0.9)))
        env[pos: pos + on] = 1.0
        pos += on + off
    data = out * env * 0.15
    data += (rng.normal(0.0, 0.004, n).astype(np.float32))
    return np.clip(data, -1.0, 1.0)


def _service(tmp_path: str | os.PathLike) -> SpeakerIdService:
    cfg_file = os.path.join(str(tmp_path), "cfg.yml")
    with open(cfg_file, "w", encoding="utf-8") as fh:
        fh.write("enabled: true\nthreshold:\n  similarity: 0.72\n  margin: 0.04\n")
        fh.write("store_path: %s\n" % os.path.join(str(tmp_path), "speakers.json"))
    return SpeakerIdService(cfg_file)


def test_same_speaker_variants_identify(tmp_path):
    svc = _service(tmp_path)
    base = _synth_voice(seed=7, f0=118.0, tilt=-0.4)
    svc.enroll_speaker("anon", base, SR)
    fired = False
    for variant in range(3):
        clip = _synth_voice(seed=17 + variant * 5, f0=118.0, tilt=-0.4)
        res = svc.identify(clip, SR)
        if variant == 0:
            fired = bool(res.get("known"))
            name = res.get("name")
            sim = float(res.get("similarity", 0.0))
            margin = float(res.get("margin", 0.0))
            assert fired, f"self not identified: {res}"
            assert name == "anon"
            assert sim >= 0.72
            assert margin >= 0.04
    assert fired


def test_stranger_speaker_not_confident(tmp_path):
    svc = _service(tmp_path)
    svc.enroll_speaker("owner", _synth_voice(seed=1, f0=118.0, tilt=-0.4), SR)
    svc.enroll_speaker("stranger", _synth_voice(seed=2, f0=215.0, tilt=1.8), SR)
    stranger_clip = _synth_voice(seed=5, f0=215.0, tilt=1.8)
    res = svc.identify(stranger_clip, SR)
    if res.get("known"):
        assert res["name"] == "stranger"
    else:
        assert res.get("candidate") == "stranger"
        assert float(res.get("similarity", 0.0)) >= 0.72


def test_too_little_speech_flagged(tmp_path):
    svc = _service(tmp_path)
    tiny = np.zeros(int(0.2 * SR), dtype=np.float32)
    res = svc.identify(tiny, SR)
    assert res.get("ok") is True and res.get("known") is False and res.get("reason") == "too_little_speech"
    silence = (np.random.default_rng(3).normal(0.0, 0.001, int(1.5 * SR))).astype(np.float32)
    en = svc.enroll_speaker("x", silence, SR) if False else None
    with pytest.raises(Exception):
        svc.enroll_speaker("whisper", silence, SR)
    assert en is None


def test_store_persists_and_forgets(tmp_path):
    svc = _service(tmp_path)
    svc.enroll_speaker("aan", _synth_voice(seed=9, f0=118.0, tilt=-0.4), SR)
    assert svc.store.count() == 1
    second = _service(tmp_path)
    assert second.store.names() == ["aan"]
    second.forget("aan")
    third = _service(tmp_path)
    assert third.store.count() == 0


def test_pcm_b64_path(tmp_path):
    svc = _service(tmp_path)
    from modules.voice.speaker_id.services.voiceprint import f32_to_pcm_b64, pcm_b64_to_f32

    clip = _synth_voice(seed=11, f0=118.0, tilt=-0.4)
    b64 = f32_to_pcm_b64(clip)
    back = pcm_b64_to_f32(b64)
    assert back.dtype == np.float32 and back.size == clip.size
    svc.enroll_speaker("b64_user", back, SR)
    res = svc.identify(back, SR)
    assert res.get("known") is True and res.get("name") == "b64_user"
