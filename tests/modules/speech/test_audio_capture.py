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


def test_vu_normalization_uses_configured_noise_floor_and_ceiling() -> None:
    capture = AudioCapture({
        "channels": 2,
        "frame_ms": 30,
        "vu": {"window_ms": 90, "noise_floor": 100, "speech_ceiling": 5000},
    })
    capture._rms_left_window.extend([80, 100, 1000])
    capture._rms_right_window.extend([40, 80, 90])
    left, right = capture.get_rms_levels()
    assert 0.4 < left < 0.8
    assert right == 0.0


def test_merge_config_updates_vu_channel_gain_and_window() -> None:
    capture = AudioCapture({"channels": 2, "frame_ms": 30})
    capture.merge_config({
        "vu": {
            "window_ms": 60,
            "noise_floor": 100,
            "speech_ceiling": 5000,
            "left_gain": 1.0,
            "right_gain": 2.0,
        }
    })
    capture._rms_left_window.append(500)
    capture._rms_right_window.append(500)
    left, right = capture.get_rms_levels()
    assert capture._rms_left_window.maxlen == 2
    assert right > left
