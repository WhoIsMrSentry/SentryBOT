"""Companion line generator tests."""
from __future__ import annotations

from modules.autonomy.services.companion_lines import CompanionLineGenerator


def test_ritual_morning_needs_fallback():
    gen = CompanionLineGenerator(None, {"use_llm": False})
    line = gen._needs_line("ritual_morning", {"dominant_emotion": "joy"})
    assert "günaydın" in line.lower() or "Günaydın" in line
