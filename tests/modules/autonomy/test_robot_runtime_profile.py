from __future__ import annotations

import json
from pathlib import Path

from modules.autonomy.services import robot_runtime_profile as profile


ROOT = Path(__file__).resolve().parents[3]


def test_pi_runtime_profile_contract_markers():
    assert profile.PI_RUNTIME_PROFILE_CONTRACT is True
    assert profile.PI_RUNTIME_PROFILE_BOUNDARY_ROLE == "pi_robot_runtime_profile_resolver"
    assert profile.PI_RUNTIME_PROFILE_CONFIG_PATH == "config/robot_execution_profiles.json"


def test_profile_config_exists_and_loads():
    path = profile.profile_config_path(ROOT)
    assert path.exists(), path

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "profiles" in raw

    cfg = profile.load_profile_config(ROOT)
    assert cfg["ok"] is True
    assert isinstance(cfg["profiles"], dict)


def test_pc_dev_keeps_config_active_mode_safe():
    env = {"SENTRYBOT_RUNTIME_TARGET": "pc"}
    st = profile.status(ROOT, env)
    assert st["ok"] is True
    assert st["target"]["target"] == "pc_dev"
    assert st["profile_name"]
    assert st["read_only"] is True
    assert st["armed"] is False
    assert st["hardware_enabled"] is False


def test_pi_robot_target_prefers_robot_safe_preview_not_pc_dry_run():
    env = {"SENTRYBOT_RUNTIME_TARGET": "pi"}
    st = profile.status(ROOT, env)
    assert st["ok"] is True
    assert st["target"]["target"] == "pi_robot"
    assert st["profile_name"] == "robot_safe_preview"
    assert st["profile_name"] != "pc_dry_run"
    assert st["read_only"] is True
    assert st["armed"] is False
    assert st["hardware_enabled"] is False


def test_explicit_profile_override_still_does_not_arm():
    env = {
        "SENTRYBOT_RUNTIME_TARGET": "pi",
        "SENTRYBOT_EXECUTION_PROFILE": "robot_safe_manual",
    }
    st = profile.status(ROOT, env)
    assert st["ok"] is True
    assert st["profile_name"] == "robot_safe_manual"
    assert st["requires_arm_gate"] is True
    assert st["armed"] is False
    assert st["hardware_enabled"] is False


def test_invalid_explicit_profile_falls_back_to_robot_safe_preview():
    env = {
        "SENTRYBOT_RUNTIME_TARGET": "pi",
        "SENTRYBOT_EXECUTION_PROFILE": "__missing__",
    }
    resolved = profile.resolve_runtime_profile(ROOT, env)
    assert resolved["ok"] is True
    assert resolved["profile_name"] == "robot_safe_preview"
    assert "invalid_explicit_profile:__missing__" in resolved["warnings"]
