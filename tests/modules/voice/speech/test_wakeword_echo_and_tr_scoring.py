from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.voice.speak.services.lang_detect import detect_text_language
from modules.voice.speech.api.router import get_router as get_speech_router
from modules.voice.speech.services.audio_filters import SoftwareEchoGate, SpeechAudioFilterMixin
from modules.voice.speech.services.online_stt import transcribe_google_multilang
from modules.voice.speech.services.recognizer import RecognitionResult, Recognizer
from modules.voice.speech.services.wake_phrase import (
    is_wakeword_echo_transcript,
    strip_wakeword_prefix,
)
from modules.voice.speech.xSpeechService import SpeechService
from modules.voice.wakeword.services.wakeword_actions import WakewordActions


def test_phonetic_wakeword_echo_vs_genuine_topics() -> None:
    # Unambiguous phonetic variants always detected
    assert is_wakeword_echo_transcript("hey maykroft", recent_wakeword=False) is True
    assert is_wakeword_echo_transcript("hey my craft", recent_wakeword=False) is True

    # Contextual hallucinations suppressed right after openWakeWord trigger
    for echo in ("Hey Minecraft", "a Microsoft", "am I correct", "play Minecraft", "Minecraft"):
        assert is_wakeword_echo_transcript(echo, wakeword="hey_mycroft_v0.1", recent_wakeword=True) is True

    # Real topics outside the wakeword echo window must NOT be dropped
    assert is_wakeword_echo_transcript("Minecraft nedir", wakeword="hey_mycroft_v0.1", recent_wakeword=False) is False
    assert is_wakeword_echo_transcript("Microsoft nasıl kuruldu", wakeword="", recent_wakeword=False) is False

    # Leading wakeword prefix is cleanly stripped while preserving real command
    assert strip_wakeword_prefix("Hey Mycroft saat kaç?") == "saat kaç?"
    assert strip_wakeword_prefix("Hey Minecraft bugünkü hava nasıl", include_phonetic=True) == "bugünkü hava nasıl"


def test_speech_service_and_router_drop_post_wakeword_echo() -> None:
    svc = SpeechService()
    try:
        actions = WakewordActions({"stop_on_final": True})
        actions._speech_service = svc

        svc._utterance_pcm.extend(b"\x01\x00" * 800)
        actions.start_speech(wakeword="hey_mycroft_v0.1")
        assert len(svc._utterance_pcm) == 0
        assert svc.was_wakeword_triggered_recently(window_s=3.5) is True

        # Post-wakeword hallucination in last_result must NOT prematurely close wakeword window
        actions._speech_service = SimpleNamespace(
            last_result={"text": "Hey Minecraft", "final": True, "ts": 500.0}
        )
        assert actions.has_final_speech(since_ts=400.0, wakeword="hey_mycroft_v0.1") is False

        # Router drops post-wakeword echo before publishing /speech/last or notifying autonomy
        app = FastAPI()
        app.include_router(get_speech_router(svc))
        cb = svc._default_result_cb
        assert cb is not None

        cb(RecognitionResult(text="Hey Minecraft", is_final=True, confidence=0.9, language="tr"))
        client = TestClient(app)
        assert client.get("/speech/last").json().get("text") is None

        # Combined wakeword + Turkish command strips prefix and resolves language to 'tr'
        cb(RecognitionResult(text="Hey Minecraft bugünkü hava nasıl", is_final=True, confidence=0.9, language="en"))
        last = client.get("/speech/last").json()
        assert last["text"] == "bugünkü hava nasıl"
        assert last["language"] == "tr"
    finally:
        svc.stop()


def test_recognizer_request_reset_discards_pre_wakeword_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_pcms: list[bytes] = []
    rec = Recognizer(
        {
            "language": "tr",
            "samplerate": 16000,
            "channels": 1,
            "min_utterance_sec": 0.15,
            "silence_threshold": 130.0,
            "vad": {"hangover_ms": 350},
        }
    )
    rec._ensure_model = lambda: None

    def _fake_recognize(pcm: bytes):
        captured_pcms.append(pcm)
        return "saati söyle", "tr"

    monkeypatch.setattr(rec, "recognize_pcm", _fake_recognize)

    # Pre-wakeword loud chunks (e.g. "Hey Mycroft") filled into buffer before trigger, then silence, then command
    pre_wake = np.full(480, 1800, dtype=np.int16).tobytes()
    cmd_loud = np.full(480, 2200, dtype=np.int16).tobytes()
    silent = np.zeros(480, dtype=np.int16).tobytes()

    def _stream():
        for _ in range(10):
            yield pre_wake
        rec.request_reset(drop_sec=0.12)
        for _ in range(4):
            yield pre_wake  # trailing edge of wakeword dropped cleanly (4 * 0.03s = 0.12s)
        for _ in range(10):
            yield cmd_loud
        for _ in range(20):
            yield silent

    results = list(rec.run(_stream()))
    assert len(results) == 1
    assert results[0].text == "saati söyle"
    # Pre-wakeword samples (1800) must have been flushed; captured command contains 2200 amplitudes
    assert len(captured_pcms) == 1
    arr = np.frombuffer(captured_pcms[0], dtype=np.int16)
    assert np.any(arr == 2200)
    assert not np.any(arr == 1800)


def test_echo_suppressed_tts_frames_do_not_trigger_stt_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Harness(SpeechAudioFilterMixin):
        def __init__(self) -> None:
            self.cfg = {"direction": {"enabled": False}}
            self.capture = SimpleNamespace(cfg=SimpleNamespace(channels=1, dtype="int16"))
            self._direction = None
            self._last_angle = None
            self._last_angle_ts = 0.0
            self._last_audio_level = 0.0
            self._tracking = False
            self._pan = None
            self._stt_input_gain = 1.2
            self._auto_language = True
            self._utterance_pcm = bytearray()
            self._max_utterance_bytes = 32000
            self._last_frame_echo_suppressed = False
            self._echo_gate = SoftwareEchoGate(suppression_gain=0.12, barge_in_ratio=2.2, hold_time_s=0.45)
            self._echo_gate.set_tts_playback(True, estimated_rms=1200.0)

    h = _Harness()
    rec = Recognizer(
        {"language": "tr", "samplerate": 16000, "channels": 1, "min_utterance_sec": 0.15, "silence_threshold": 130.0},
        should_suppress_speech_fn=lambda: bool(h._last_frame_echo_suppressed),
    )
    rec._ensure_model = lambda: None
    called = 0

    def _fail_rec(_pcm: bytes):
        nonlocal called
        called += 1
        return "Minecraft", "tr"

    monkeypatch.setattr(rec, "recognize_pcm", _fail_rec)

    # Simulate TTS speaker echo RMS=1500 (< 1200 * 2.2 = 2640) while TTS plays: must NOT trigger STT
    echo_chunk = np.full(480, 1500, dtype=np.int16).tobytes()
    results = list(rec.run(h._direction_wrapper([echo_chunk] * 30)))
    assert results == []
    assert called == 0


def test_turkish_preferred_over_weak_english_hallucinations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "modules.voice.speech.services.online_stt.sr",
        SimpleNamespace(AudioData=lambda pcm, sample_rate=16000, sample_width=2: (pcm, sample_rate, sample_width)),
    )
    monkeypatch.setattr("modules.voice.speech.services.online_stt._recognizer", object())

    def _mock_pairs(tr_text: str, en_text: str):
        def _fake(_audio, lang_tag: str):
            return (tr_text, lang_tag) if lang_tag.startswith("tr") else (en_text, lang_tag)

        return _fake

    # ASCII Turkish vs weak EN hallucination ("a Microsoft" / "need contacts" / "am I correct")
    for tr_cand, en_cand in (
        ("selam dostum", "a Microsoft"),
        ("saat kac oldu", "need contacts"),
        ("bugun ne yapiyorsun", "am I correct"),
        ("isiklari kapat", "play Minecraft"),
    ):
        monkeypatch.setattr("modules.voice.speech.services.online_stt.transcribe_single_language", _mock_pairs(tr_cand, en_cand))
        text, lang = transcribe_google_multilang(b"\x01\x00" * 2000, languages=["tr", "en"], default_lang="tr")
        assert lang == "tr", f"Expected tr for ({tr_cand!r} vs {en_cand!r}), got {lang!r} ({text!r})"
        assert text == tr_cand

    # Real multi-word English still beats Turkish gibberish
    monkeypatch.setattr(
        "modules.voice.speech.services.online_stt.transcribe_single_language",
        _mock_pairs("parayı entrika görsel", "please introduce yourself"),
    )
    text_en, lang_en = transcribe_google_multilang(b"\x01\x00" * 2000, languages=["tr", "en"], default_lang="tr")
    assert lang_en == "en"
    assert text_en == "please introduce yourself"

    # Helper sanity checks
    assert detect_text_language("a Microsoft", default="tr") == "tr"
    assert detect_text_language("bugun ne yapiyorsun", default="en") == "tr"
    assert detect_text_language("Please check the weather today.", default="tr") == "en"


def test_vocal_mixin_strips_leading_wakeword_before_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.autonomy.services.brain import AutonomyBrain

    brain = AutonomyBrain({"llm": {"enabled": False}})
    brain.client = MagicMock()
    routed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        brain,
        "_try_agent_core_path",
        lambda text, lang, speaker, request_id: routed.append((text, lang)) or True,
    )

    brain._react_to_speech("Hey Mycroft saat kaç?", source_lang="en")
    assert routed == [("saat kaç?", "tr")]

    routed.clear()
    brain._react_to_speech("Hey Mycroft", source_lang="tr")
    assert routed == []

