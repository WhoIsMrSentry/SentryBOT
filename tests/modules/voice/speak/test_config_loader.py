from __future__ import annotations

from pathlib import Path

from modules.voice.speak.config_loader import load_config


def test_load_config_supports_shorthand_engine_key(tmp_path: Path) -> None:
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
speak:
  engine: xtts
  tts:
    language: tr
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(agent_cfg))

    assert cfg["tts"]["engine"] == "xtts"
    assert cfg["tts"]["language"] == "tr"


def test_load_config_shorthand_engine_overrides_nested_engine(tmp_path: Path) -> None:
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
speak:
  engine: xtts
  tts:
    engine: pyttsx3
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(agent_cfg))

    assert cfg["tts"]["engine"] == "xtts"
