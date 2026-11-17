"""Verification tests for Iteration 22: CI safety gates, systemd/env parity, workflow & conftest isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_robot_safe_manual_gate_rejects_empty_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tools.ci.robot_safe_manual_gate as gate

    fake_cfg = tmp_path / "config" / "robot_execution_profiles.json"
    fake_cfg.parent.mkdir(parents=True)
    fake_cfg.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    assert gate.profile_present() is False

    fake_cfg.write_text(json.dumps({"profiles": {"raspberry_pi": {"allow_real_hardware": True}}}), encoding="utf-8")
    assert gate.profile_present() is True

    # Real repo config must also pass cleanly without any `or True` bypass
    monkeypatch.setattr(gate, "ROOT", ROOT)
    assert gate.profile_present() is True
    assert gate.main(["--skip-matrix"]) == 0


def test_env_example_and_systemd_alignment():
    import tools.ci.robot_safety_ci_guard as guard

    ok, detail = guard.check_env_example_consistency(ROOT)
    assert ok is True, detail

    systemd_env = (ROOT / "deploy" / "systemd" / "sentrybot.env.example").read_text(encoding="utf-8")
    assert "SENTRYBOT_PROFILE=robot" in systemd_env
    assert "SENTRYBOT_PROFILE=pi_robot" not in systemd_env

    unit = (ROOT / "deploy" / "systemd" / "sentrybot.service").read_text(encoding="utf-8")
    assert "scripts/run_robot.py" in unit
    assert "User=sentrybot" in unit
    assert "Group=sentrybot" in unit
    assert "SENTRYBOT_ROOT=" in unit and ":-__PROJECT_ROOT__" in unit


def test_ci_workflow_and_pyproject_consolidated():
    assert not (ROOT / ".github" / "workflows" / "tests.yml").exists()
    assert not (ROOT / "pytest.ini").exists()
    assert not (ROOT / "tests" / "integration_test.py").exists()
    assert not (ROOT / "pi_runtime_stub_legacy_caller_audit.json").exists()
    assert not (ROOT / "PI_RUNTIME_STUB_LEGACY_CALLER_AUDIT.md").exists()

    wf = (ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    assert "tests/modules/*" in wf
    assert "modules/*/tests" not in wf
    assert "services/remote_multimodal_server/tests" in wf
    assert "services/remote_tts_server/tests" in wf
    assert "robot_safety_ci_guard.py" in wf
    assert "--profile ci" in wf

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.pytest.ini_options]" in pyproject
    assert '"B006"' in pyproject and '"UP034"' in pyproject


def test_companion_ci_guard_uses_real_target_or_skip(monkeypatch: pytest.MonkeyPatch):
    import tools.ci.companion_ci_guard as ccg

    rc = ccg.main(["--skip-tests"])
    assert rc == 0


def test_conftest_isolates_state_and_data_writes(pytestconfig):
    # During normal pytest run (`--smoke-real` false), temp file written into data/ is cleaned by conftest fixture
    if pytestconfig.getoption("--smoke-real", default=False):
        pytest.skip("Explicit --smoke-real skips rollback isolation")

    sentinel = ROOT / "data" / "__iteration22_isolation_probe.sqlite3"
    assert not sentinel.exists()
    # Clean up handled on teardown in conftest even if a test creates top-level data/*.sqlite3
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"temp-db")
    assert sentinel.is_file()


def test_conftest_cleanup_removed_previous_probe():
    assert not (ROOT / "data" / "__iteration22_isolation_probe.sqlite3").exists()
