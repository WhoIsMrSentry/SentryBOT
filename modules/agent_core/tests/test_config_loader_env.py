from __future__ import annotations

from pathlib import Path

from modules.agent_core.config_loader import load_config


def test_agent_core_load_config_uses_external_ollama_env(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "agent_config.yml"
    cfg_file.write_text(
        """
agent:
  model: llama3.2:3b
  cooldown_s: 1.0
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.99:11435")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:8b")
    monkeypatch.setenv("AGENT_COOLDOWN_S", "2.5")

    cfg = load_config(str(cfg_file))

    assert cfg["agent"]["model"] == "qwen3.5:8b"
    assert float(cfg["agent"]["cooldown_s"]) == 2.5
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["base_url"] == "http://192.168.1.99:11435"
    assert cfg["llm"]["model"] == "qwen3.5:8b"
