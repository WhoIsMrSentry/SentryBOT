from __future__ import annotations

from pathlib import Path

from modules.config_center.agent_yaml_loader import load_agent_config
from modules.config_center.runtime_profile import active_runtime_profile, apply_runtime_profile


def test_runtime_profile_merges_active_profile(tmp_path: Path):
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text(
        """
runtime_profile:
  active: google_ai_studio
  profiles:
    google_ai_studio:
      llm:
        provider: google_ai_studio
      agent:
        model: gemini-2.0-flash
agent:
  model: qwen3.5:9b
llm:
  provider: ollama
""".strip(),
        encoding="utf-8",
    )

    cfg = load_agent_config(agent_cfg)
    assert active_runtime_profile(cfg) == "google_ai_studio"
    assert cfg["llm"]["provider"] == "google_ai_studio"
    assert cfg["agent"]["model"] == "gemini-2.0-flash"


def test_apply_runtime_profile_noop_without_active():
    raw = {"agent": {"model": "x"}, "runtime_profile": {"profiles": {}}}
    out = apply_runtime_profile(dict(raw))
    assert out["agent"]["model"] == "x"
