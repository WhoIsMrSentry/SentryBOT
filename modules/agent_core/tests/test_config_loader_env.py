from __future__ import annotations

from pathlib import Path
import pytest

from modules.agent_core.config_loader import load_config


def test_agent_core_load_config_enforces_strict_single_model_policy(tmp_path: Path):
    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: qwen3.5:9b
  cooldown_s: 1.0
  request_timeout: 75
  ollama_base_url: http://127.0.0.1:11434
llm:
  provider: ollama
  model: qwen3.5:9b
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(cfg_file))

    assert cfg["agent"]["model"] == "qwen3.5:9b"
    assert float(cfg["agent"]["cooldown_s"]) == 1.0
    assert float(cfg["agent"]["request_timeout"]) == 75.0
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["model"] == "qwen3.5:9b"
    assert cfg["llm"]["single_model_mode"] is True
    assert cfg["llm"]["clm_fallback_enabled"] is False
    assert cfg["ollama"]["base_url"] == "http://127.0.0.1:11434"
    assert cfg["ollama"]["model"] == "qwen3.5:9b"


def test_agent_core_load_config_accepts_google_provider(tmp_path: Path):
    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: gemini-2.0-flash
llm:
  provider: google_ai_studio
google_ai_studio:
  model: gemini-2.0-flash
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(cfg_file))
    assert cfg["llm"]["provider"] == "google_ai_studio"
    assert cfg["agent"]["model"] == "gemini-2.0-flash"


def test_agent_core_load_config_rejects_non_qwen3_5_9b_model(tmp_path: Path):
    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: qwen3.5:8b
llm:
  provider: ollama
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(str(cfg_file))
