def test_speech_arbiter_sets_tts_state_callback():
    from modules.agent_core.services.speech_arbiter import SpeechArbiter

    states = []

    def fake_speak(text, **_kwargs):
        return {"ok": True, "text": text}

    arb = SpeechArbiter(speak_fn=fake_speak)
    arb.set_tts_state_callback(lambda active: states.append(bool(active)))
    arb.start()
    try:
        arb.enqueue_final("merhaba")
        import time
        time.sleep(0.1)
    finally:
        arb.stop()

    assert True in states
    assert False in states
