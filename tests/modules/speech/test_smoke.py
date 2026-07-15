import os


def test_imports():
    import modules.speech as speech
    assert hasattr(speech, "xSpeechService")


def test_config_load():
    from modules.speech.config_loader import load_config
    cfg = load_config()
    assert "audio" in cfg and "recognition" in cfg


def test_service_init():
    if os.environ.get("SKIP_VOSK", "1") == "1":
        return
    from modules.speech.xSpeechService import SpeechService
    svc = SpeechService()
    assert svc is not None
