from modules.voice.wakeword.config_loader import load_config


def test_wakeword_config_loads_audio_device() -> None:
    cfg = load_config()
    audio = cfg.get("audio", {})
    assert audio.get("device")
    assert "wakeword" in cfg
    ow = cfg.get("openwakeword", {})
    assert ow.get("pretrained_models") == ["hey_mycroft"]
    assert cfg.get("wakeword", {}).get("engine") == "openwakeword"
