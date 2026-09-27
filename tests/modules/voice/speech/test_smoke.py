import os


def test_imports():
    import modules.voice.speech as speech
    assert hasattr(speech, "xSpeechService")


def test_config_load():
    from modules.voice.speech.config_loader import load_config
    cfg = load_config()
    assert "audio" in cfg and "recognition" in cfg


def test_service_init():
    from modules.voice.speech.xSpeechService import SpeechService
    svc = SpeechService()
    assert svc is not None


def test_direction_and_sound_tracking():
    from modules.voice.speech.xSpeechService import SpeechService
    svc = SpeechService()
    assert svc._tracking is False
    svc.track_start()
    assert svc._tracking is True
    assert svc._direction is not None
    st = svc.track_status()
    assert st["tracking"] is True
    svc.track_stop()
    assert svc._tracking is False
