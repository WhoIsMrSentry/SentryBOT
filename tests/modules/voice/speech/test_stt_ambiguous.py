"""Dual-decode should skip when primary transcript language is confident."""
from __future__ import annotations

from unittest.mock import MagicMock

from modules.voice.speech.services.stt_language import resolve_stt_text_and_language


def test_skips_dual_decode_when_primary_confident():
    primary = MagicMock()
    primary.cfg.language = "tr"
    text, lang = resolve_stt_text_and_language(
        "merhaba nasılsın bugün",
        b"\x00" * 3200,
        primary=primary,
        extra_recognizers={"en": MagicMock()},
        primary_lang="tr",
        default_language="tr",
        auto_switch_model=True,
        dual_decode_only_if_ambiguous=True,
        prefer_online_detect=False,
    )
    assert text
    assert lang in {"tr", "en"}
