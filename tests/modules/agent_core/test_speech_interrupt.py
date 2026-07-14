from __future__ import annotations

from modules.agent_core.services.speech_arbiter import SpeechArbiter


def test_speech_arbiter_interrupt_clears_queue_and_calls_stop() -> None:
    stopped = {"count": 0}

    def _speak(**_kwargs):
        pass

    def _stop():
        stopped["count"] += 1

    arb = SpeechArbiter(speak_fn=_speak)
    arb.set_stop_playback_fn(_stop)
    arb.enqueue_progress("progress line", cancel_token="tok1")
    cleared = arb.interrupt_all()
    assert cleared >= 1
    assert stopped["count"] == 1
    assert arb.queue_size() == 0
