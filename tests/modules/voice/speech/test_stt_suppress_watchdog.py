from __future__ import annotations

import time
from modules.voice.speech.xSpeechService import SpeechService


def test_stt_suppress_watchdog_auto_expires():
    service = SpeechService()
    assert not service.is_stt_suppressed()

    # Set suppression with 0.1s TTL for fast unit testing
    service.set_stt_suppressed(True, ttl_s=0.1)
    assert service.is_stt_suppressed()

    time.sleep(0.15)
    # Watchdog should automatically expire suppression
    assert not service.is_stt_suppressed()

    # Manual un-suppress
    service.set_stt_suppressed(True, ttl_s=10.0)
    assert service.is_stt_suppressed()
    service.set_stt_suppressed(False)
    assert not service.is_stt_suppressed()
