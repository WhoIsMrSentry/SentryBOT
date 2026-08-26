from __future__ import annotations

from modules.common.runtime_target import RuntimeTarget
from modules.autonomy.services.hardware_policy import apply_runtime_hardware_policy


def test_pc_host_forces_dry_run(monkeypatch):
    monkeypatch.setattr(
        "modules.autonomy.services.robot_runtime_profile.detect_runtime_target",
        lambda: RuntimeTarget("windows", "amd64", "", False, "linux_required"),
    )
    out = apply_runtime_hardware_policy({"dry_run_default": False, "allow_real_hardware": True})
    assert out["allow_real_hardware"] is False
    assert out["dry_run_default"] is True
    assert out["runtime_reason"] == "linux_required"


def test_pi_profile_enables_real_hardware(monkeypatch):
    monkeypatch.setattr(
        "modules.autonomy.services.robot_runtime_profile.detect_runtime_target",
        lambda: RuntimeTarget("linux", "aarch64", "Raspberry Pi 5", True, "raspberry_pi_detected"),
    )
    out = apply_runtime_hardware_policy({"dry_run_default": True, "allow_real_hardware": False})
    assert out["allow_real_hardware"] is True
    assert out["dry_run_default"] is False
    assert out["runtime_profile_applied"] is True


def test_follow_runtime_profile_false_keeps_yaml(monkeypatch):
    monkeypatch.setattr(
        "modules.autonomy.services.robot_runtime_profile.detect_runtime_target",
        lambda: RuntimeTarget("linux", "aarch64", "Raspberry Pi 5", True, "raspberry_pi_detected"),
    )
    out = apply_runtime_hardware_policy(
        {"follow_runtime_profile": False, "dry_run_default": True, "allow_real_hardware": False}
    )
    assert out["allow_real_hardware"] is False
    assert out["dry_run_default"] is True
    assert out["runtime_profile_applied"] is False
