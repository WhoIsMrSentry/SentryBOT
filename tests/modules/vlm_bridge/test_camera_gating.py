from __future__ import annotations

import modules.vlm_bridge.services.processor as processor_mod
from modules.vlm_bridge.services.processor import VisionProcessor


def test_stream_not_started_when_camera_hardware_unavailable():
    proc = VisionProcessor({"vision": {"processing_mode": "local"}})
    proc.set_camera_hardware_available(False)
    proc.start_stream_processing()
    assert proc._capture_thread is None


def test_remote_mode_does_not_claim_local_camera_available():
    proc = VisionProcessor({"vision": {"processing_mode": "remote", "hybrid_local_capture": False}})
    proc.set_camera_hardware_available(False)
    assert proc.is_local_camera_available() is False


def test_set_processing_mode_local_blocked_without_hardware(monkeypatch):
    # Verify gating works cleanly even when cv2 is absent in CI
    monkeypatch.setattr(processor_mod, "cv2", None)
    proc = VisionProcessor({"vision": {"processing_mode": "remote", "follow_runtime_profile": False}})
    proc.set_camera_hardware_available(False)
    out = proc.set_processing_mode("local")
    assert out.get("ok") is False
    assert out.get("error") == "camera_disabled"
    assert proc.processing_mode == "remote"


def test_has_vision_context_uses_latest_results():
    proc = VisionProcessor({"vision": {"processing_mode": "remote", "follow_runtime_profile": False}})
    proc.latest_results = [{"label": "person", "name": "Ali"}]
    assert proc.has_vision_context() is True
