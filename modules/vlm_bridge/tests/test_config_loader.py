from __future__ import annotations

from pathlib import Path
import pytest

from modules.vlm_bridge.config_loader import load_config


def test_vlm_config_loader_uses_agent_yaml_and_derives_chat_endpoint(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: gemma4:26b
  ollama_base_url: "http://10.33.250.169:11434"
llm:
  provider: ollama
  model: gemma4:26b
ollama:
  base_url: "http://10.33.250.169:11434"
  model: gemma4:26b
vlm_bridge:
  ollama:
    timeout: 9.5
  llm:
    provider: ollama
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(base_dir=str(agent_cfg))

    assert cfg["ollama"]["endpoint"] == "http://10.33.250.169:11434/api/chat"
    assert cfg["ollama"]["model"] == "gemma4:26b"
    assert float(cfg["ollama"]["timeout"]) == 9.5
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["single_model_mode"] is True


def test_vlm_config_loader_rejects_non_ollama_provider(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: gemma4:26b
  ollama_base_url: "http://localhost:11434"
llm:
  provider: google_ai_studio
ollama:
  base_url: "http://localhost:11434"
  model: gemma4:26b
vlm_bridge:
  llm:
    provider: google_ai_studio
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(base_dir=str(agent_cfg))


def test_vlm_config_loader_rejects_non_gemma4_model(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: qwen3.5:8b
  ollama_base_url: "http://localhost:11434"
llm:
  provider: ollama
  model: qwen3.5:8b
ollama:
  base_url: "http://localhost:11434"
  model: qwen3.5:8b
vlm_bridge:
  llm:
    provider: ollama
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(base_dir=str(agent_cfg))
