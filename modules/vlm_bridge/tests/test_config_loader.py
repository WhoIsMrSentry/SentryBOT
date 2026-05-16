from __future__ import annotations

from pathlib import Path
import pytest

from modules.vlm_bridge.config_loader import load_config


def test_vlm_config_loader_uses_agent_yaml_and_derives_chat_endpoint(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: qwen3.5:9b
  ollama_base_url: "http://10.33.250.169:11434"
llm:
  provider: ollama
  model: qwen3.5:9b
ollama:
  base_url: "http://10.33.250.169:11434"
  model: qwen3.5:9b
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
    assert cfg["ollama"]["model"] == "qwen3.5:9b"
    assert float(cfg["ollama"]["timeout"]) == 9.5
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["single_model_mode"] is True


def test_vlm_config_loader_accepts_google_provider(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: gemini-2.0-flash
llm:
  provider: google_ai_studio
google_ai_studio:
  model: gemini-2.0-flash
  request_timeout: 30
ollama:
  base_url: "http://127.0.0.1:11434"
  model: qwen3.5:9b
vlm_bridge:
  llm:
    provider: google_ai_studio
  vision_llm:
    provider: google_ai_studio
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(base_dir=str(agent_cfg))
    assert cfg["llm"]["provider"] == "google_ai_studio"
    assert cfg["vision_llm"]["provider"] == "google_ai_studio"
    assert cfg["ollama"]["model"] == "gemini-2.0-flash"


def test_vlm_config_loader_rejects_non_qwen3_5_9b_model(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: llama3.1:8b
  ollama_base_url: "http://127.0.0.1:11434"
llm:
  provider: ollama
  model: llama3.1:8b
ollama:
  base_url: "http://127.0.0.1:11434"
  model: llama3.1:8b
vlm_bridge:
  llm:
    provider: ollama
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(base_dir=str(agent_cfg))
