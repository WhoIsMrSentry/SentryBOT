from __future__ import annotations

import json
import time

import numpy as np

from modules.arduino_serial.contract import validate_arduino_payload
from modules.voice.speak.services import lcd_sync as lcd_mod
from modules.voice.speak.services.lcd_sync import SpeechLcdSync, paginate_lcd_text, sanitize_lcd_text
from modules.voice.speak.services.pcm import PCM
from modules.voice.speak.xSpeakService import SpeakService


def test_sanitize_and_paginate_20x4():
    cleaned = sanitize_lcd_text('Merhaba "dünya", şğüöç İ!\\test')
    assert cleaned == "Merhaba 'dunya', sguoc I! test" or cleaned == "Merhaba 'dunya', sguoc I!/test"
    assert '"' not in cleaned
    assert "\\" not in cleaned

    sample = (
        "Merhaba Emir, bugun hava cok guzel gorunuyor ve kamerada bir kisi tespit ettim "
        "simdi internette arastiriyorum."
    )
    pages = paginate_lcd_text(sample, cols=20, rows=4)
    assert len(pages) >= 2
    for page in pages:
        assert len(page) == 4
        for row in page:
            assert len(row) <= 20
        wire = json.dumps({"cmd": "lcd", "l1": page[0], "l2": page[1], "l3": page[2], "l4": page[3], "overlay": True})
        assert len(wire) < 256


def test_lcd_sync_pages_over_duration_and_debounces_restore():
    sent = []
    sync = SpeechLcdSync(
        {
            "enabled": True,
            "cols": 20,
            "rows": 4,
            "min_page_sec": 0.05,
            "restore_delay_s": 0.08,
        },
        send_fn=lambda payload: (sent.append(payload) or True),
    )
    try:
        long_text = (
            "Birinci cumlede uzun metin yaziyoruz ki yirmi carpı dort ekranda iki sayfa olussun "
            "ve konusma suresi boyunca sayfalar gecsin."
        )
        tok1 = sync.begin_utterance(long_text, duration_sec=0.25)
        assert tok1 is not None
        time.sleep(0.32)
        sync.end_utterance(tok1, interrupted=False)

        # Immediately start chunk 2 before restore_delay_s -> NO restore in between!
        tok2 = sync.begin_utterance("Ikinci kisa cumle.", duration_sec=0.1)
        assert tok2 is not None
        assert not any(p.get("restore") for p in sent)

        time.sleep(0.05)
        sync.end_utterance(tok2, interrupted=False)
        time.sleep(0.18)

        assert any(p.get("restore") is True and p.get("overlay") is True for p in sent)
        assert len([p for p in sent if not p.get("restore")]) >= 3
        for payload in sent:
            assert validate_arduino_payload(payload) is None
    finally:
        sync.close()


def test_lcd_sync_barge_in_restores_immediately_and_wires_into_speak(monkeypatch):
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    sent = []
    expr_events = []

    svc = SpeakService.__new__(SpeakService)
    svc.cfg = {"tts": {"engine": "piper"}, "audio_out": {"samplerate": 22050, "channels": 1}, "liveliness": {"enabled": True}}
    svc._liveliness_cfg = {"enabled": True}
    svc._synth_lock = __import__("threading").RLock()
    svc._play_lock = __import__("threading").RLock()
    svc._speech_lock = svc._synth_lock
    svc._is_speaking = False
    svc._playback_listeners = []
    svc._playback_listeners_lock = __import__("threading").Lock()
    svc._expr_session = None
    svc.stream_max_chunk_chars = 180
    svc.lcd_sync = SpeechLcdSync(
        {"enabled": True, "cols": 20, "rows": 4, "restore_delay_s": 0.05},
        send_fn=lambda payload: (sent.append(payload) or True),
    )

    class _FakeTTS:
        @staticmethod
        def synthesize(text, overrides=None):
            return PCM(data=np.zeros(4410, dtype=np.float32), samplerate=22050, channels=1)

    class _FakePlayer:
        cfg = type("Cfg", (), {"samplerate": 22050, "channels": 1})()
        is_stopped = False

        @staticmethod
        def play_blocking(pcm):
            time.sleep(0.05)
            return 0.2

        @staticmethod
        def stop_playback():
            return None

    svc.tts = _FakeTTS()
    svc.player = _FakePlayer()
    svc._expression_event = lambda ev, data=None: expr_events.append((ev, data))  # type: ignore

    res = svc.speak("Kamerada Emir var ve ekran acik.")
    assert res["ok"] is True
    time.sleep(0.12)

    started_evs = [d for ev, d in expr_events if ev == "speak.started"]
    assert started_evs and started_evs[0]["text"] == "Kamerada Emir var ve ekran acik."
    assert started_evs[0]["duration_sec"] >= 0.19
    assert any(p.get("l1") and "Kamerada Emir" in p["l1"] for p in sent)
    assert any(p.get("restore") is True for p in sent)

    # Interrupt mid-speech restores immediately
    sent.clear()
    _FakePlayer.is_stopped = True
    tok = svc.lcd_sync.begin_utterance("Kesilecek cok uzun cumle " * 5, duration_sec=2.0)
    time.sleep(0.03)
    svc.lcd_sync.end_utterance(tok, interrupted=True)
    time.sleep(0.06)
    assert any(p.get("restore") is True for p in sent)
    svc.lcd_sync.close()
    assert lcd_mod is not None
