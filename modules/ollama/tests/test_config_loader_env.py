from __future__ import annotations

from pathlib import Path

from modules.ollama.config_loader import load_config


def test_load_config_applies_ollama_env_overrides(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text(
        """
llm:
  provider: ollama
ollama:
  base_url: http://localhost:11435
  model: llama3.2:3b
  request_timeout: 30
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.25:11435")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "90")

    cfg = load_config(str(cfg_file))

    assert cfg["ollama"]["base_url"] == "http://10.0.0.25:11435"
    assert cfg["ollama"]["model"] == "qwen3.5:4b"
    assert float(cfg["ollama"]["request_timeout"]) == 90.0


def test_load_config_applies_provider_override(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("llm: {provider: ollama}", encoding="utf-8")

    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    cfg = load_config(str(cfg_file))

    assert cfg["llm"]["provider"] == "google_ai_studio"
