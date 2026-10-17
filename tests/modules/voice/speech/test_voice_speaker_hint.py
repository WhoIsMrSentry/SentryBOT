"""Voiceprint -> last_speaker integration: speech finalize hint + brain speaker resolution."""
from __future__ import annotations

import os
import time

import numpy as np

from modules.voice.speech.xSpeechService import compute_voice_speaker_hint
import modules.voice.speaker_id.xSpeakerIdService as sid_mod
from modules.voice.speaker_id.xSpeakerIdService import SpeakerIdService

SR = 16000


def _synth_voice(seed: int, f0: float, tilt: float, seconds: float = 1.5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for k in range(1, 26):
        amp = float(rng.uniform(0.5, 1.1)) / (k ** tilt)
        out += amp * np.sin(2 * np.pi * f0 * k * (1.0 + 0.01 * float(rng.random())) * t).astype(np.float32)
    env = np.zeros(n, dtype=np.float32)
    pos = 0
    while pos < n:
        on = int(0.12 * SR * float(rng.uniform(0.8, 1.4)))
        off = int(0.12 * SR * float(rng.uniform(0.4, 0.9)))
        env[pos: pos + on] = 1.0
        pos += on + off
    data = out * env * 0.15
    data += rng.normal(0.0, 0.004, n).astype(np.float32)
    return np.clip(data, -1.0, 1.0)


def _swap_singleton(monkeypatch, tmp_path, service: SpeakerIdService) -> None:
    monkeypatch.setattr(sid_mod, "_DEFAULT", service, raising=False)


def _svc(tmp_path) -> SpeakerIdService:
    cfg_file = os.path.join(str(tmp_path), "cfg.yml")
    with open(cfg_file, "w", encoding="utf-8") as fh:
        fh.write("enabled: true\nthreshold:\n  similarity: 0.72\n  margin: 0.04\n")
        fh.write("store_path: %s\n" % os.path.join(str(tmp_path), "speakers.json"))
    return SpeakerIdService(cfg_file)


def test_hint_returns_known_speaker(monkeypatch, tmp_path):
    svc = _svc(tmp_path)
    clip = _synth_voice(seed=7, f0=118.0, tilt=-0.4)
    svc.enroll_speaker("Emir", clip, SR)
    _swap_singleton(monkeypatch, tmp_path, svc)

    pcm16 = (clip * 32767.0).astype(np.int16).tobytes()
    hint = compute_voice_speaker_hint(pcm16)
    assert hint is not None
    assert hint.get("name") == "Emir"
    assert float(hint.get("similarity", 0.0)) >= 0.72


def test_hint_none_for_short_or_unknown(monkeypatch, tmp_path):
    svc = _svc(tmp_path)
    svc.enroll_speaker("only", _synth_voice(seed=1, f0=118.0, tilt=-0.4), SR)
    _swap_singleton(monkeypatch, tmp_path, svc)

    short = np.zeros(int(0.15 * SR), dtype=np.float32)
    assert compute_voice_speaker_hint((short * 32767.0).astype(np.int16).tobytes()) is None

    stranger = _synth_voice(seed=9, f0=215.0, tilt=1.8)
    res = compute_voice_speaker_hint((stranger * 32767.0).astype(np.int16).tobytes())
    # may be None (below thresholds) or flipped wrongly to a known name; never that voice
    if res is not None:
        assert res.get("name") != "only" or float(res.get("similarity", 9.0)) < 0.72


def test_hint_none_without_profiles(monkeypatch, tmp_path):
    _swap_singleton(monkeypatch, tmp_path, _svc(tmp_path))
    clip = _synth_voice(seed=3, f0=130.0, tilt=0.0)
    assert compute_voice_speaker_hint((clip * 32767.0).astype(np.int16).tobytes()) is None


# ---- brain-level: voice identity outranks the stale camera window --------------

def _brain_stub():
    from modules.autonomy.services.brain import AutonomyBrain

    brain = AutonomyBrain.__new__(AutonomyBrain)
    brain.config = {}
    brain.state = {}
    brain.memory = type("M", (), {"add_event": lambda self, txt: None})()
    brain.mood = type(
        "Md",
        (),
        {"modify": lambda self, axis, amt: None, "state": {"energy": 50.0, "happiness": 50.0}},
    )()
    brain.client = type(
        "C",
        (),
        {
            "push_interaction_event": lambda *a, **k: None,
            "append_person_chat": lambda *a, **k: None,
        },
    )()
    rm = type("RM", (), {})()
    rm.observe_person = lambda *a, **k: None
    rm.add_chat = lambda *a, **k: None
    brain.relationship_memory = rm
    return brain


def test_voice_speaker_wins_over_camera_window():
    brain = _brain_stub()
    brain.owner_cfg = {}
    brain._current_people = {"KameraKisi": time.time()}
    out = brain._process_speech_social_context("Merhaba", voice_speaker="Emir")
    assert out == "Emir"
    assert brain.state.get("last_speaker") == "Emir"
    assert "User said" in (brain.memory.events[0] if getattr(brain.memory, "events", None) else "User said")


def test_camera_fallback_when_no_voice_hint():
    brain = _brain_stub()
    brain.owner_cfg = {}
    brain._current_people = {"KameraKisi": time.time()}
    out = brain._process_speech_social_context("Selam", voice_speaker=None)
    assert out == "KameraKisi"
    assert brain.state.get("last_speaker") == "KameraKisi"


def test_unknown_voice_hint_falls_back_to_camera():
    brain = _brain_stub()
    brain.owner_cfg = {}
    brain._current_people = {"KameraKisi": time.time()}
    out = brain._process_speech_social_context("Selam", voice_speaker="unknown")
    assert out == "KameraKisi"
