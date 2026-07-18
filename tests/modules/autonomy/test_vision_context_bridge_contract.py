from __future__ import annotations

from pathlib import Path

from modules.autonomy.services.vision_context_bridge import (
    VISION_CONTEXT_BRIDGE_CONTRACT,
    VISION_CONTEXT_BRIDGE_ROLE,
    VISION_CONTEXT_BRIDGE_STATUS_ONLY,
    VisionContextBridge,
    build_vision_context,
)


def test_vision_context_bridge_is_status_only_contract():
    assert VISION_CONTEXT_BRIDGE_CONTRACT is True
    assert VISION_CONTEXT_BRIDGE_ROLE == "camera_vlm_to_autonomy_semantic_context_adapter"
    assert VISION_CONTEXT_BRIDGE_STATUS_ONLY is True

    bridge = VisionContextBridge(history_limit=4)
    context = bridge.ingest_camera_status(
        {"enabled": False, "running": False, "has_frame": False, "reason": "disabled"},
        now=1.0,
    )
    assert context["kind"] == "camera_status"
    assert context["enabled"] is False
    assert context["running"] is False
    assert context["has_frame"] is False
    assert bridge.latest() == context


def test_vlm_result_is_normalized_without_inference_call():
    bridge = VisionContextBridge(history_limit=4)
    context = bridge.ingest_vlm_result(
        {
            "caption": "owner near desk",
            "objects": ["desk", "cup"],
            "people": ["owner"],
            "scene": "room",
            "risk": "none",
            "confidence": 0.8,
        },
        now=2.0,
    )
    assert context["kind"] == "vlm_semantic_context"
    assert context["caption"] == "owner near desk"
    assert context["objects"] == ["desk", "cup"]
    assert context["people"] == ["owner"]
    assert context["risk"] == "none"


def test_bundle_reports_no_activation_started():
    bundle = build_vision_context(
        camera_status={"enabled": True, "running": False, "has_frame": False},
        vlm_result={"labels": ["person"]},
        now=3.0,
    )
    assert bundle["kind"] == "vision_context_bundle"
    assert bundle["status_only"] is True
    assert bundle["activation_started"] is False
    assert len(bundle["entries"]) == 2


def test_bridge_source_does_not_contain_capture_or_network_starts():
    source = Path("modules/autonomy/services/vision_context_bridge.py").read_text(encoding="utf-8")
    forbidden = [
        "VideoCapture(",
        "cv2.",
        "requests.",
        "httpx.",
        "/camera/start",
        "/camera/snap",
        "/camera/video",
        "/vlm/analyze",
        "/vlm/caption",
    ]
    for token in forbidden:
        assert token not in source
