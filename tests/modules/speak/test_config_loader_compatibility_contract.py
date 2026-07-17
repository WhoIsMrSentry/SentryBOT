from __future__ import annotations

from modules.speak.config_loader import (
    SPEAK_CONFIG_COMPATIBILITY_CONTRACT,
    SPEAK_CONFIG_COMPATIBILITY_ROLE,
    _normalize_speak_section,
)


def test_speak_engine_shorthand_maps_to_tts_engine_without_local_config():
    cfg = _normalize_speak_section({
        "engine": "piper",
        "tts": {
            "engine": "pyttsx3",
            "piper": {"model_path": "data/piper_models/test.onnx"},
        },
    })
    assert SPEAK_CONFIG_COMPATIBILITY_CONTRACT is True
    assert SPEAK_CONFIG_COMPATIBILITY_ROLE == "agent_yaml_shorthand_alias_normalizer"
    assert cfg["tts"]["engine"] == "piper"
    assert cfg["tts"]["piper"]["model_path"].endswith("data\\piper_models\\test.onnx") or cfg["tts"]["piper"]["model_path"].endswith("data/piper_models/test.onnx")


def test_speak_tts_section_is_preserved_when_no_shorthand_engine():
    cfg = _normalize_speak_section({"tts": {"engine": "remote", "timeout": 5}})
    assert cfg["tts"]["engine"] == "remote"
    assert cfg["tts"]["timeout"] == 5


def test_non_dict_piper_section_normalizes_safely():
    cfg = _normalize_speak_section({"engine": "piper", "tts": {"piper": "bad"}})
    assert cfg["tts"]["engine"] == "piper"
    assert cfg["tts"].get("piper") == "bad"
