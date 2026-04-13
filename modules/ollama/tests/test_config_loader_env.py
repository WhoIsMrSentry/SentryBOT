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


def test_load_config_inherits_vlm_primary_model_hint(monkeypatch, tmp_path: Path):
    vlm_cfg = tmp_path / "vlm_config.yml"
    vlm_cfg.write_text(
        """
llm:
  provider: ollama
  single_model_mode: true
  primary_model: gemma-4-26B-A4B
""".strip(),
        encoding="utf-8",
    )

    ollama_cfg = tmp_path / "ollama_config.yml"
    ollama_cfg.write_text(
        """
llm:
  provider: ollama
ollama:
  model: llama3.2:3b
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("VLM_CFG", str(vlm_cfg))
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    cfg = load_config(str(ollama_cfg))

    assert cfg["llm"]["single_model_mode"] is True
    assert cfg["ollama"]["model"] == "gemma-4-26B-A4B"
