from __future__ import annotations

from pathlib import Path
import pytest

from modules.ollama.config_loader import load_config


def test_load_config_reads_strict_agent_yaml_sections(tmp_path: Path):
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
  request_timeout: 72
ollama_service:
  server:
    host: 0.0.0.0
    port: 9001
  persona:
    default: sentry
    dir: modules/ollama/config/personalities
  actions:
    endpoint: http://localhost:8080/autonomy/apply_actions
    default_apply: true
    timeout: 1.5
  translation:
    enabled: true
    default_source_lang: tr
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(agent_cfg))

    assert cfg["ollama"]["base_url"] == "http://10.33.250.169:11434"
    assert cfg["ollama"]["model"] == "gemma4:26b"
    assert float(cfg["ollama"]["request_timeout"]) == 72.0
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["single_model_mode"] is True
    assert int(cfg["server"]["port"]) == 9001


def test_load_config_rejects_non_ollama_provider(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: gemma4:26b
llm:
  provider: google_ai_studio
ollama:
  base_url: "http://localhost:11434"
  model: gemma4:26b
ollama_service:
  persona:
    default: sentry
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(str(agent_cfg))


def test_load_config_rejects_non_gemma4_model(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: qwen3.5:8b
llm:
  provider: ollama
ollama:
  base_url: "http://localhost:11434"
  model: qwen3.5:8b
ollama_service:
  persona:
    default: sentry
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(str(agent_cfg))
