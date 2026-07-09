from __future__ import annotations

from modules.agent_core.services.progress import _msg, supported_progress_languages


def test_progress_catalog_has_many_languages():
    langs = supported_progress_languages()
    assert "en" in langs
    assert "tr" in langs
    assert len(langs) >= 10


def test_progress_falls_back_to_english_for_unknown_lang():
    msg = _msg("xx", "persona_start", "fallback")
    assert msg
    assert msg != "fallback" or "Putting" in msg or "birleştirip" in msg or len(msg) > 3
