"""Tests for Google STT HTTP/executor timeout bounds so network stalls cannot freeze listening."""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest

from modules.voice.speech.services import online_stt
from modules.voice.speech.services.recognizer import Recognizer


def test_default_recognizer_has_finite_operation_timeout() -> None:
    if online_stt._recognizer is not None and hasattr(online_stt._recognizer, "operation_timeout"):
        assert online_stt._recognizer.operation_timeout is not None
        assert float(online_stt._recognizer.operation_timeout) > 0.0

    rec = Recognizer({"language": "tr", "samplerate": 16000})
    if rec._sr_recognizer is not None:
        assert rec._sr_recognizer.operation_timeout is not None
        assert float(rec._sr_recognizer.operation_timeout) > 0.0


def test_transcribe_google_multilang_returns_within_timeout_on_stalled_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        online_stt,
        "sr",
        SimpleNamespace(
            AudioData=lambda pcm, sample_rate=16000, sample_width=2: (pcm, sample_rate, sample_width),
            UnknownValueError=ValueError,
            RequestError=OSError,
        ),
    )
    monkeypatch.setattr(online_stt, "_recognizer", object())

    def _stalled_or_fast(_audio, lang_tag: str):
        if lang_tag.startswith("en"):
            time.sleep(2.5)
            return "too late", lang_tag
        return "selam sentry", lang_tag

    monkeypatch.setattr(online_stt, "transcribe_single_language", _stalled_or_fast)

    t0 = time.monotonic()
    text, lang = online_stt.transcribe_google_multilang(
        b"\x01\x00" * 2000,
        languages=["tr", "en"],
        default_lang="tr",
        timeout_s=0.15,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0
    assert text == "selam sentry"
    assert lang == "tr"


def test_recognizer_run_continues_after_timeout_in_recognize_pcm(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recognizer(
        {
            "language": "tr",
            "samplerate": 16000,
            "channels": 1,
            "min_utterance_sec": 0.2,
            "vad": {"hangover_ms": 300},
        }
    )
    rec._ensure_model = lambda: None  # type: ignore[method-assign]

    calls = {"n": 0}

    def _flaky_recognize(_pcm: bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("simulated stt timeout")
        return "ikinci komut", "tr"

    monkeypatch.setattr(rec, "recognize_pcm", _flaky_recognize)

    loud = np.full(480, 1500, dtype=np.int16).tobytes()
    silent = np.zeros(480, dtype=np.int16).tobytes()
    stream = ([loud] * 12 + [silent] * 16) * 2

    results = list(rec.run(stream))
    assert calls["n"] >= 2
    assert any(r.text == "ikinci komut" for r in results)
