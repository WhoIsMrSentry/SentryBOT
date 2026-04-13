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
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "75")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AGENT_COOLDOWN_S", "2.5")
    monkeypatch.setenv("AGENT_MAX_STEPS", "7")
    monkeypatch.setenv("AGENT_TRI_LAYER_ENABLED", "true")
    monkeypatch.setenv("AGENT_ROUTER_MAX_SUBAGENTS", "3")
    monkeypatch.setenv("AGENT_SUBAGENT_MAX_STEPS", "4")
    monkeypatch.setenv("AGENT_PERSONA_NUM_PREDICT", "280")

    cfg = load_config(str(cfg_file))

    assert cfg["agent"]["model"] == "qwen3.5:8b"
    assert float(cfg["agent"]["cooldown_s"]) == 2.5
    assert float(cfg["agent"]["request_timeout"]) == 75.0
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["base_url"] == "http://192.168.1.99:11435"
    assert cfg["llm"]["model"] == "qwen3.5:8b"
    assert int(cfg["agent"]["max_steps"]) == 7
    assert cfg["tri_layer"]["enabled"] is True
    assert int(cfg["tri_layer"]["router"]["max_subagents"]) == 3
    assert int(cfg["tri_layer"]["subagent"]["max_steps"]) == 4
    assert int(cfg["tri_layer"]["persona"]["num_predict"]) == 280


def test_agent_core_keeps_explicit_provider_when_ollama_base_url_is_set(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "agent_config.yml"
    cfg_file.write_text(
        """
agent:
  model: gemma-4-26B-A4B
llm:
  provider: google_ai_studio
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    cfg = load_config(str(cfg_file))

    assert cfg["llm"]["provider"] == "google_ai_studio"
    assert cfg["llm"]["base_url"] == "http://localhost:11434"
