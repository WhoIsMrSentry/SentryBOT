from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.voice.speak.xSpeakService import SpeakService
from modules.voice.speech.api.router import get_router as get_speech_router
from modules.voice.speech.services.audio_filters import SoftwareEchoGate, SpeechAudioFilterMixin
from modules.voice.speech.services.pan_tilt import PanTiltController
from modules.voice.speech.services.recognizer import RecognitionResult, Recognizer
from modules.voice.speech.services.sound_tracking import SpeechSoundTrackingMixin
from modules.voice.speech.services.stt_language import resolve_stt_text_and_language
from modules.voice.speech.services.turn_taking import DynamicTurnTakingEngine, TurnState
from modules.voice.speech.xSpeechService import SpeechService


def test_direction_disabled_still_runs_downmix_gain_echo_and_utterance_buffer() -> None:
    class _FilterHarness(SpeechAudioFilterMixin):
        def __init__(self) -> None:
            self.cfg = {"direction": {"enabled": False}}
            self.capture = SimpleNamespace(cfg=SimpleNamespace(channels=2, dtype="int16"))
            self._direction = None
            self._last_angle = None
            self._last_audio_level = 0.0
            self._tracking = False
            self._pan = None
            self._stt_input_gain = 1.0
            self._auto_language = True
            self._utterance_pcm = bytearray()
            self._max_utterance_bytes = 32000
            self._echo_gate = SoftwareEchoGate(suppression_gain=0.1, barge_in_ratio=2.5)
            self._echo_gate.set_tts_playback(True, estimated_rms=1000.0)

    h = _FilterHarness()
    stereo = np.full((160, 2), 600, dtype=np.int16).tobytes()
    out_chunks = list(h._direction_wrapper([stereo]))

    assert len(out_chunks) == 1
    mono = out_chunks[0]
    # Downmixed to mono (half byte count) even when direction.enabled=False
    assert len(mono) == len(stereo) // 2
    assert h._last_audio_level > 0.0
    # Attenuated by SoftwareEchoGate
    arr = np.frombuffer(mono, dtype=np.int16)
    assert np.max(np.abs(arr)) <= 100
    assert bytes(h._utterance_pcm) == mono


def test_speech_recognizer_mono_and_single_google_stt_path(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = SpeechService()
    try:
        assert svc.recognizer.cfg.channels == 1

        stt_calls = 0

        def _fail_if_called(*_a, **_kw):
            nonlocal stt_calls
            stt_calls += 1
            return "duplicate", "tr"

        monkeypatch.setattr(
            "modules.voice.speech.services.online_stt.transcribe_google_multilang",
            _fail_if_called,
        )
        svc._utterance_pcm.extend(b"\x01\x00" * 1600)

        app = FastAPI()
        app.include_router(get_speech_router(svc))
        # Grab registered default callback set by router
        cb = svc._default_result_cb
        assert cb is not None
        cb(RecognitionResult(text="merhaba sentry", is_final=True, confidence=0.9, language="tr"))

        # Must NOT issue a second Google STT call when Recognizer already resolved text & lang
        assert stt_calls == 0
        assert len(svc._utterance_pcm) == 0

        client = TestClient(app)
        last = client.get("/speech/last").json()
        assert last["text"] == "merhaba sentry"
        assert last["language"] == "tr"
    finally:
        svc.stop()


def test_recognizer_integrates_turn_taking_and_intonation_decay(monkeypatch: pytest.MonkeyPatch) -> None:
    cues: list[dict] = []
    rec = Recognizer(
        {
            "language": "tr",
            "samplerate": 16000,
            "channels": 1,
            "min_utterance_sec": 0.2,
            "vad": {"hangover_ms": 400},
        },
        on_turn_cue=cues.append,
    )
    rec._ensure_model = lambda: None  # bypass SpeechRecognition requirement in offline unit test
    monkeypatch.setattr(rec, "recognize_pcm", lambda pcm: ("komut alındı", "tr"))

    loud = np.full(480, 1500, dtype=np.int16).tobytes()  # 30 ms mono @16kHz
    silent = np.zeros(480, dtype=np.int16).tobytes()
    stream = [loud] * 15 + [silent] * 20

    results = list(rec.run(stream))
    assert len(results) == 1
    assert results[0].text == "komut alındı"
    assert results[0].language == "tr"

    # Low energy decay accelerates turn completion slightly vs sustained edge
    tt = DynamicTurnTakingEngine(min_speech_duration_s=0.3, end_of_turn_silence_s=0.8)
    tt.start_listening(current_time_s=0.0)
    tt.process_vad_frame(True, current_time_s=0.1, energy_rms=2000.0)
    tt.process_vad_frame(True, current_time_s=0.5, energy_rms=2000.0)
    # Silence at +0.62s (<0.8s baseline, >= 0.8 * 0.75 = 0.6s decayed floor) completes cleanly
    res = tt.process_vad_frame(False, current_time_s=1.12, energy_rms=50.0)
    assert res["state"] == TurnState.USER_DONE
    assert res["turn_completed"] is True


def test_stt_language_tuple_decode_and_margin() -> None:
    secondary = MagicMock()
    secondary.recognize_pcm.return_value = ("please check the weather", "en")
    text, lang = resolve_stt_text_and_language(
        "merhaba",
        b"\x01\x00" * 1600,
        primary=MagicMock(),
        secondary=secondary,
        primary_lang="tr",
        default_language="tr",
        auto_switch_model=True,
        dual_decode_only_if_ambiguous=False,
        dual_decode_margin=0.2,
        prefer_online_detect=False,
    )
    assert lang == "en"
    assert text == "please check the weather"

    # Huge margin must prevent secondary from overturning primary
    sec_blocked = MagicMock()
    sec_blocked.recognize_pcm.return_value = ("hello world", "en")
    text2, lang2 = resolve_stt_text_and_language(
        "merhaba bugün",
        b"\x01\x00" * 1600,
        primary=MagicMock(),
        secondary=sec_blocked,
        primary_lang="tr",
        default_language="tr",
        auto_switch_model=True,
        dual_decode_only_if_ambiguous=False,
        dual_decode_margin=50.0,
        prefer_online_detect=False,
    )
    assert lang2 == "tr"
    assert text2 == "merhaba bugün"


def test_speech_stop_joins_thread_and_stt_status_lists_all_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = SpeechService()
    try:
        svc.cfg.setdefault("recognition", {})["language_models"] = {"en": {}, "de": {}}
        st = svc.stt_status()
        assert "en" in st["languages"] and "de" in st["languages"]

        entered = threading.Event()

        class _BlockingCapture:
            def stream(self, stop_event=None):
                entered.set()
                while stop_event is not None and not stop_event.is_set():
                    time.sleep(0.01)
                return iter(())

        svc._audio_router = SimpleNamespace(get_capture=lambda: _BlockingCapture(), start=lambda: True)
        svc.recognizer.status = lambda: {"ok": True, "language": "tr"}
        svc.recognizer.run = lambda s: (x for x in s if False)

        svc.start_background()
        assert entered.wait(timeout=1.0)
        svc.stop()
        assert svc.listening is False
        assert svc._thread is None

        # PanTiltController.stop joins thread cleanly
        pt = PanTiltController({"update_hz": 50.0})
        pt.start()
        assert pt._thr is not None and pt._thr.is_alive()
        pt.stop()
        assert pt._thr is None
    finally:
        svc.stop()


def test_speak_to_speech_echo_bridge_and_sound_tracking_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    speak = SpeakService()
    speech = SpeechService()
    try:
        assert speech.attach_speak_service(speak) is True
        speak._notify_playback_listeners(True, 1400.0)
        assert speech._echo_gate is not None
        assert speech._echo_gate._tts_playing is True
        assert speech._echo_gate._estimated_echo_rms == pytest.approx(1400.0)

        speak.stop()
        assert speech._echo_gate._tts_playing is False
    finally:
        speech.stop()

    # Sound tracking min_delta_deg throttle + persistent session
    class _TrackHarness(SpeechSoundTrackingMixin):
        def __init__(self) -> None:
            self.cfg = {"pan_tilt": {"min_delta_deg": 2.0, "use_head_arbiter": True}}
            self._pan = None
            self._tracking = True
            self._last_angle = 0.0
            self._head_arbiter = None
            self._pan_http_session = None
            self._last_sent_pan_deg = None

    posted: list[float] = []
    monkeypatch.setattr(
        "requests.post",
        lambda url, json=None, timeout=0.25: posted.append(float((json or {})["pan"])),
    )
    th = _TrackHarness()
    th._send_pan(90.0)
    th._send_pan(91.0)  # < 2.0 deg delta -> throttled
    th._send_pan(95.0)  # >= 2.0 deg delta -> sent
    assert posted == [90.0, 95.0]
