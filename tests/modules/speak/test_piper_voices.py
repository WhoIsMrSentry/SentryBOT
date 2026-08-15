from __future__ import annotations

from pathlib import Path

from modules.speak.config_loader import _resolve_piper_paths
from modules.speak.services.lang_detect import (
    detect_text_language,
    piper_voice_for_language,
    resolve_speak_language,
)
from modules.speak.services.tts import DummyBackend, TextToSpeech, PersistentPiperModel, TTSConfig, PiperBackend

def test_resolve_piper_voice_entry(monkeypatch) -> None:
    class DummyPiperVoice:
        @classmethod
        def load(cls, *args, **kwargs):
            return cls()
    monkeypatch.setattr("modules.speak.services.tts.Path.is_file", lambda self: True)
    monkeypatch.setattr("modules.speak.services.tts._load_piper_api", lambda: (DummyPiperVoice, None))
    cfg = {
        "voice": "glados",
        "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
        "voices": {
            "glados": {
                "model_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx",
                "config_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx.json",
            },
        },
    }
    model = PersistentPiperModel(TTSConfig(), cfg, cfg["voices"]["glados"])
    assert model.model_path.endswith("glados_piper_medium.onnx")


def test_resolve_piper_paths_expands_repo_relative() -> None:
    piper = _resolve_piper_paths(
        {
            "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
            "voices": {
                "tr": {
                    "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
                },
            },
        }
    )
    assert Path(piper["model_path"]).is_absolute()
    assert Path(piper["voices"]["tr"]["model_path"]).is_absolute()


def test_detect_english_question() -> None:
    assert detect_text_language("What is the weather today?") == "en"


def test_detect_turkish_text() -> None:
    assert detect_text_language("Bugün hava nasıl?") == "tr"


def test_resolve_speak_language_prefers_spoken_text_over_stt_hint() -> None:
    lang = resolve_speak_language(
        "The answer is forty-two.",
        explicit="tr",
        default="tr",
        prefer_text=True,
    )
    assert lang == "en"


def test_piper_voice_for_language_maps_en_to_glados() -> None:
    piper_cfg = {
        "voice": "tr",
        "language_voices": {"tr": "tr", "en": "glados"},
        "voices": {"tr": {}, "glados": {}},
    }
    assert piper_voice_for_language("en", piper_cfg) == "glados"
    assert piper_voice_for_language("tr", piper_cfg) == "tr"


def test_text_to_speech_piper_picks_english_voice_key() -> None:
    tts = TextToSpeech(
        {
            "engine": "piper",
            "language": "tr",
            "piper": {
                "voice": "tr",
                "auto_language": True,
                "language_voices": {"tr": "tr", "en": "glados"},
                "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
                "voices": {
                    "tr": {"model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx"},
                    "glados": {"model_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx"},
                },
            },
        }
    )
    if not isinstance(tts.backend, PiperBackend):
        return
    voice = tts._resolve_piper_voice("Hello, how can I help you?", tts._base_cfg, {"language": "tr"})
    assert voice == "glados"


def test_piper_missing_model_falls_back_to_dummy(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    tts = TextToSpeech({
        "engine": "piper",
        "allow_dummy_fallback": True,
        "piper": {
            "model_path": "data/piper_models/__missing__/model.onnx",
        },
    })
    assert isinstance(tts.backend, DummyBackend)
