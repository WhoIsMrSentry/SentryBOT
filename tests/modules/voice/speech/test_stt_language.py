from __future__ import annotations

from unittest.mock import MagicMock

from modules.voice.speak.services.tts import TextToSpeech
from modules.voice.speech.services.stt_language import resolve_stt_text_and_language


def test_resolve_stt_keeps_turkish_on_primary() -> None:
    primary = MagicMock()
    text, lang = resolve_stt_text_and_language(
        "bugün hava nasıl",
        b"",
        primary=primary,
        secondary=None,
        default_language="tr",
    )
    assert lang == "tr"
    assert text == "bugün hava nasıl"


def test_resolve_stt_picks_en_over_tr_garbage() -> None:
    secondary = MagicMock()
    secondary.recognize_pcm.return_value = "please introduce yourself"
    text, lang = resolve_stt_text_and_language(
        "parayı entrika görsel",
        b"\x00\x01" * 200,
        primary=MagicMock(),
        secondary=secondary,
        default_language="tr",
    )
    assert lang == "en"
    assert "introduce" in text.lower()
    secondary.recognize_pcm.assert_called_once()


def test_piper_locks_voice_from_explicit_language() -> None:
    tts = TextToSpeech(
        {
            "engine": "piper",
            "language": "tr",
            "piper": {
                "voice": "tr",
                "auto_language": True,
                "lock_session_language": True,
                "language_voices": {"tr": "tr", "en": "glados"},
                "model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx",
                "voices": {
                    "tr": {"model_path": "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx"},
                    "glados": {"model_path": "data/piper_models/en-glados-medium/glados_piper_medium.onnx"},
                },
            },
        }
    )
    from modules.voice.speak.services.lang_detect import piper_voice_for_language

    voice = tts._resolve_piper_voice(
        "Merhaba nasılsın",
        tts._base_cfg,
        {"language": "en"},
    )
    assert voice == "glados"
