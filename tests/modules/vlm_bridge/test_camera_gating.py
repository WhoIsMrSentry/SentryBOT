from __future__ import annotations

import importlib.util

import pytest


def _cv2_importable() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except Exception:
        return False


_cv2_missing = not _cv2_importable()


@pytest.mark.skipif(_cv2_missing, reason="cv2 not installed")
def test_stream_not_started_when_camera_hardware_unavailable():
    from modules.vlm_bridge.services.processor import VisionProcessor

    proc = VisionProcessor({"vision": {"processing_mode": "local"}})
    proc.set_camera_hardware_available(False)
    proc.start_stream_processing()
    assert proc._capture_thread is None


@pytest.mark.skipif(_cv2_missing, reason="cv2 not installed")
def test_remote_mode_does_not_claim_local_camera_available():
    from modules.vlm_bridge.services.processor import VisionProcessor

    proc = VisionProcessor({"vision": {"processing_mode": "remote", "hybrid_local_capture": False}})
    proc.set_camera_hardware_available(False)
    assert proc.is_local_camera_available() is False


@pytest.mark.skipif(_cv2_missing, reason="cv2 not installed")
def test_set_processing_mode_local_blocked_without_hardware():
    from modules.vlm_bridge.services.processor import VisionProcessor

    proc = VisionProcessor({"vision": {"processing_mode": "remote", "follow_runtime_profile": False}})
    proc.set_camera_hardware_available(False)
    out = proc.set_processing_mode("local")
    assert out.get("ok") is False
    assert out.get("error") == "camera_disabled"
    assert proc.processing_mode == "remote"


@pytest.mark.skipif(_cv2_missing, reason="cv2 not installed")
def test_has_vision_context_uses_latest_results():
    from modules.vlm_bridge.services.processor import VisionProcessor

    proc = VisionProcessor({"vision": {"processing_mode": "remote", "follow_runtime_profile": False}})
    proc.latest_results = [{"label": "person", "name": "Ali"}]
    assert proc.has_vision_context() is True
