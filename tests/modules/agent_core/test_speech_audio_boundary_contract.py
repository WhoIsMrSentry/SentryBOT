from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from modules.agent_core.services.speech_arbiter import (
    SpeechArbiter,
    SpeechItem,
    SpeechPriority,
    split_sentences,
)


ROOT = Path(__file__).resolve().parents[3]


def _probe_import(module: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def _expired_value(item: SpeechItem) -> bool:
    attr = getattr(item, "expired")
    return bool(attr() if callable(attr) else attr)


def test_speech_audio_boundary_marker_present():
    import modules.agent_core.services.speech_arbiter as speech_arbiter

    assert speech_arbiter.SPEECH_AUDIO_COMPATIBILITY is True
    assert speech_arbiter.SPEECH_AUDIO_BOUNDARY_ROLE == "agent_core_compat_speech_arbiter"


def test_light_speech_audio_import_has_no_runtime_console_side_effect():
    proc = _probe_import("modules.agent_core.services.speech_arbiter")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", proc.stdout
    assert "Runtime console initialized" not in proc.stdout


def test_split_sentences_and_speech_item_contract():
    chunks = split_sentences("Bir. Iki? Uc!", max_chars=80, max_chunks=8)
    assert chunks[:3] == ["Bir.", "Iki?", "Uc!"]

    long_chunks = split_sentences("alpha beta gamma delta", max_chars=8, max_chunks=8)
    assert long_chunks
    assert all(isinstance(part, str) and part.strip() for part in long_chunks)

    fresh = SpeechItem(text="hello", max_age_s=30.0)
    assert _expired_value(fresh) is False

    stale = SpeechItem(text="old", max_age_s=0.0)
    time.sleep(0.002)
    assert _expired_value(stale) is True


def test_speech_arbiter_queue_cancel_and_status_contract():
    arbiter = SpeechArbiter(max_queue_size=3)

    assert arbiter.is_speaking() is False
    assert arbiter.queue_size() == 0
    status = arbiter.get_status()
    assert status["speaking"] is False
    assert status["queue_size"] == 0
    assert status["current"] is None

    first = arbiter.enqueue_progress("BakÄ±yorum", cancel_token="req-162", language="tr")
    assert isinstance(first, str) and first

    duplicate = arbiter.enqueue_progress("BakÄ±yorum", cancel_token="req-162", language="tr")
    assert isinstance(duplicate, str) and duplicate
    assert duplicate != first

    assert arbiter.queue_size() == 2
    assert arbiter.cancel_by_token("req-162") == 2
    assert arbiter.queue_size() == 0

    arbiter.enqueue_progress("Progress one", cancel_token="progress")
    arbiter.enqueue_safety("Safety one")
    assert arbiter.queue_size() == 2
    assert arbiter.cancel_progress() == 1
    assert arbiter.queue_size() == 1
    assert arbiter.clear_queue() == 1
    assert arbiter.queue_size() == 0



def test_speech_arbiter_interrupt_contract():
    events = []

    arbiter = SpeechArbiter(max_queue_size=3)
    arbiter.set_stop_playback_fn(lambda: events.append("stop_playback"))
    arbiter.set_tts_state_callback(lambda active: events.append(("tts_active", bool(active))))

    arbiter.enqueue_progress("Queued progress", cancel_token="req")
    assert arbiter.queue_size() == 1

    cleared = arbiter.interrupt_all()
    assert isinstance(cleared, int)
    assert arbiter.queue_size() == 0
    assert arbiter.is_speaking() is False
    assert "stop_playback" in events
    assert ("tts_active", False) in events


def test_speech_arbiter_start_stop_contract():
    arbiter = SpeechArbiter(max_queue_size=3)
    arbiter.start()
    try:
        status = arbiter.get_status()
        assert isinstance(status, dict)
        assert "speaking" in status
        assert "queue_size" in status
    finally:
        arbiter.stop()

    assert arbiter.is_speaking() is False
