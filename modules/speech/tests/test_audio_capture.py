from modules.speech.services.audio_capture import AudioCapture


def test_merge_config_keeps_device_when_override_is_null() -> None:
    capture = AudioCapture({"device": "plughw:0,0", "samplerate": 16000, "channels": 2})
    capture.merge_config({"device": None, "samplerate": 16000})
    assert capture.cfg.device == "plughw:0,0"


def test_merge_config_applies_explicit_device() -> None:
    capture = AudioCapture({"device": "default", "samplerate": 16000, "channels": 1})
    capture.merge_config({"device": "plughw:1,0"})
    assert capture.cfg.device == "plughw:1,0"


def test_is_alsa_device_name() -> None:
    from modules.speech.services.audio_capture import _is_alsa_device_name

    assert _is_alsa_device_name("plughw:0,0")
    assert _is_alsa_device_name("hw:1,0")
    assert not _is_alsa_device_name("0")
    assert not _is_alsa_device_name(None)
