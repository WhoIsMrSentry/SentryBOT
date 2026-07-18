from __future__ import annotations

from pathlib import Path

from modules.runtime_console.tui import ProjectData, blockers_from_lines, box


def test_blocker_detection():
    lines = [
        "Google AI Studio selected but api_key is missing",
        "piper unavailable falling back to dummy",
        "Vosk TR model missing at path",
        "ESP bridge unreachable after 5 failures",
    ]
    blockers = blockers_from_lines(lines)
    assert "AI: Google API key missing" in blockers
    assert "TTS: Piper voice model missing" in blockers
    assert "AUDIO: Turkish Vosk model missing" in blockers
    assert "MOVE: ESP bridge unreachable" in blockers


def test_box_width():
    rendered = box(" TEST ", ["hello"], 40)
    assert rendered[0].startswith("+-")
    assert len(rendered[0]) == 40


def test_config_discovery(tmp_path: Path):
    root = tmp_path
    (root / "run_robot.py").write_text("", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "agent.yaml").write_text("a: 1\n", encoding="utf-8")
    data = ProjectData(root)
    assert any(p.name == "agent.yaml" for p in data.config_files())
