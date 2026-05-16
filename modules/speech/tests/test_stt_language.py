from __future__ import annotations

from unittest.mock import MagicMock

from modules.speech.services.stt_language import resolve_stt_text_and_language


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
    primary.recognize_pcm.assert_not_called()


def test_resolve_stt_redecodes_english_with_secondary() -> None:
    primary = MagicMock()
    secondary = MagicMock()
    secondary.recognize_pcm.return_value = "what is the weather today"
    text, lang = resolve_stt_text_and_language(
        "what is the weather",
        b"\x00\x01" * 100,
        primary=primary,
        secondary=secondary,
        default_language="tr",
        auto_switch_model=True,
    )
    assert lang == "en"
    assert "weather" in text
    secondary.recognize_pcm.assert_called_once()
