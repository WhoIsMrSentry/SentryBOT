from __future__ import annotations

from pathlib import Path

from modules.vlm_bridge.config_loader import load_config


def test_vlm_config_loader_enforces_single_model_policy(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yml"
    cfg_file.write_text(
        """
llm:
  provider: ollama
  single_model_mode: true
  primary_model: gemma-4-26B-A4B
ollama:
  model: llama3.2:3b
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(base_dir=str(tmp_path))

    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["single_model_mode"] is True
    assert cfg["ollama"]["model"] == "gemma-4-26B-A4B"


def test_vlm_config_loader_env_primary_model_override(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yml"
    cfg_file.write_text(
        """
llm:
  single_model_mode: true
  primary_model: gemma-4-26B-A4B
ollama:
  model: gemma-4-26B-A4B
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("VLM_PRIMARY_MODEL", "qwen3.5:8b")

    cfg = load_config(base_dir=str(tmp_path))

    assert cfg["ollama"]["model"] == "qwen3.5:8b"


def test_vlm_config_loader_inherits_agent_yaml_ollama_url(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    cfg_file = cfg_dir / "config.yml"
    cfg_file.write_text(
        """
ollama:
  endpoint: "http://localhost:8080/ollama/chat"
""".strip(),
        encoding="utf-8",
    )

    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  ollama_base_url: "http://10.33.250.169:11434"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("AGENT_CFG", str(agent_cfg))
    monkeypatch.delenv("VLM_OLLAMA_CHAT_ENDPOINT", raising=False)

    cfg = load_config(base_dir=str(tmp_path))

    assert cfg["ollama"]["endpoint"] == "http://10.33.250.169:11434/api/chat"
