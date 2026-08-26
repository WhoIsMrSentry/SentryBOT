from __future__ import annotations

from pathlib import Path

import yaml


def test_inject_runtime_secrets_prefers_env():
    from modules.system_control.config_center.runtime_secrets import inject_runtime_secrets

    cfg = inject_runtime_secrets(
        {"agent": {"auth_token": ""}},
        env={"SENTRYBOT_AGENT_AUTH_TOKEN": "from-env"},
    )
    assert cfg["agent"]["auth_token"] == "from-env"


def test_committed_agent_yaml_auth_tokens_are_empty():
    raw = yaml.safe_load(Path("config/agent.yaml").read_text(encoding="utf-8")) or {}
    agent_token = str((raw.get("agent") or {}).get("auth_token") or "").strip()
    vlm_token = str(((raw.get("vlm_bridge") or {}).get("remote") or {}).get("auth_token") or "").strip()
    tts_token = str(
        ((((raw.get("speak") or {}).get("tts") or {}).get("remote") or {}).get("auth_token") or "")
    ).strip()
    assert agent_token == ""
    assert vlm_token == ""
    assert tts_token == ""
