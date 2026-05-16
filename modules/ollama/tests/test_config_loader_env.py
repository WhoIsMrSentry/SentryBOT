from __future__ import annotations

from pathlib import Path
import pytest

from modules.ollama.config_loader import load_config


def test_load_config_reads_strict_agent_yaml_sections(tmp_path: Path):
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
    assert cfg["ollama"]["model"] == "qwen3.5:9b"
    assert float(cfg["ollama"]["request_timeout"]) == 72.0
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["single_model_mode"] is True
    assert int(cfg["server"]["port"]) == 9001


def test_load_config_accepts_google_provider(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: gemini-2.0-flash
llm:
  provider: google_ai_studio
google_ai_studio:
  model: gemini-2.0-flash
ollama:
  base_url: "http://127.0.0.1:11434"
  model: qwen3.5:9b
ollama_service:
  persona:
    default: sentry
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(agent_cfg))
    assert cfg["llm"]["provider"] == "google_ai_studio"
    assert cfg["google_ai_studio"]["model"] == "gemini-2.0-flash"


def test_load_config_rejects_non_qwen3_5_9b_model(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
agent:
  model: qwen3.5:8b
llm:
  provider: ollama
ollama:
  base_url: "http://127.0.0.1:11434"
  model: qwen3.5:8b
ollama_service:
  persona:
    default: sentry
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(str(agent_cfg))
