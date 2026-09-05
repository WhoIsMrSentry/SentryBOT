from modules.common.runtime_target import RuntimeTarget
from modules.vlm_bridge.services.runtime_vision import apply_runtime_vision_profile


def test_pc_keeps_yaml_vision(monkeypatch):
    monkeypatch.setattr(
        "modules.autonomy.services.robot_runtime_profile.detect_runtime_target",
        lambda: RuntimeTarget("windows", "amd64", "", False, "linux_required"),
    )
    out = apply_runtime_vision_profile({"processing_mode": "remote", "hybrid_local_capture": False})
    assert out["processing_mode"] == "remote"
    assert out["hybrid_local_capture"] is False


def test_pi_applies_production_local(monkeypatch):
    monkeypatch.setattr(
        "modules.autonomy.services.robot_runtime_profile.detect_runtime_target",
        lambda: RuntimeTarget("linux", "aarch64", "Raspberry Pi 5", True, "raspberry_pi_detected"),
    )
    out = apply_runtime_vision_profile({"processing_mode": "remote", "hybrid_local_capture": False})
    assert out["processing_mode"] == "local"
    assert out["hybrid_local_capture"] is True
