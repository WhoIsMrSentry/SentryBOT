"""Companion line generator tests."""
from __future__ import annotations

from modules.autonomy.services.companion_lines import CompanionLineGenerator


def test_ritual_morning_needs_fallback():
    gen = CompanionLineGenerator(None, {"use_llm": False})
    line = gen._needs_line("ritual_morning", {"dominant_emotion": "joy"})
    assert "günaydın" in line.lower() or "Günaydın" in line


def test_homeostatic_fatigue_lines():
    gen = CompanionLineGenerator(None, {"use_llm": False})
    # Low battery line
    line_bat = gen._needs_line("idle", {"battery_pct": 10.0})
    assert "pilim" in line_bat.lower() or "şarja" in line_bat.lower()

    # High cpu temp line
    line_cpu = gen._needs_line("idle", {"cpu_temp": 80.0})
    assert "işlemcim" in line_cpu.lower() or "soğumaya" in line_cpu.lower()

