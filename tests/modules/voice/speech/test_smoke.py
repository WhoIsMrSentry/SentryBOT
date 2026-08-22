import os


def test_imports():
    import modules.voice.speech as speech
    assert hasattr(speech, "xSpeechService")


def test_config_load():
    from modules.voice.speech.config_loader import load_config
    cfg = load_config()
    assert "audio" in cfg and "recognition" in cfg


def test_service_init():
    if os.environ.get("SKIP_VOSK", "1") == "1":
        return
    from modules.voice.speech.xSpeechService import SpeechService
    svc = SpeechService()
    assert svc is not None
