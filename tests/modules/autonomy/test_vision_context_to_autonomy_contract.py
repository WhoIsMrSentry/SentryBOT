from __future__ import annotations

import ast
from pathlib import Path

from modules.autonomy.services.vision_context_to_autonomy import (
    VISION_CONTEXT_TO_AUTONOMY_CONTRACT,
    VISION_CONTEXT_TO_AUTONOMY_ROLE,
    VISION_CONTEXT_TO_AUTONOMY_STATUS_ONLY_SAFE,
    VisionContextToAutonomyAdapter,
    build_autonomy_vision_signal,
)


SOURCE_PATH = Path("modules/autonomy/services/vision_context_to_autonomy.py")


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def test_vision_context_to_autonomy_contract_markers():
    assert VISION_CONTEXT_TO_AUTONOMY_CONTRACT is True
    assert VISION_CONTEXT_TO_AUTONOMY_ROLE == "status_only_vision_semantics_to_autonomy_signal_adapter"
    assert VISION_CONTEXT_TO_AUTONOMY_STATUS_ONLY_SAFE is True


def test_camera_status_context_maps_to_safe_unavailable_signal():
    signal = build_autonomy_vision_signal(
        {
            "kind": "camera_status",
            "enabled": False,
            "running": False,
            "has_frame": False,
        },
        now=1.0,
    )

    assert signal["activation_started"] is False
    assert signal["status_only"] is True
    assert "vision_unavailable_keep_audio_memory_behaviour" in signal["goal_hints"]
    assert signal["needs_bias"]["visual_confidence"] == 0.0


def test_vlm_semantic_context_maps_to_autonomy_hints():
    signal = build_autonomy_vision_signal(
        {
            "kind": "vision_context_bundle",
            "entries": [
                {
                    "kind": "vlm_semantic_context",
                    "caption": "owner near desk",
                    "people": ["owner"],
                    "objects": ["cup", "desk"],
                    "scene": "room",
                    "risk": "none",
                    "confidence": 0.8,
                }
            ],
        },
        now=2.0,
    )

    assert "attend_to_known_person" in signal["goal_hints"]
    assert "inspect_interesting_object" in signal["goal_hints"]
    assert signal["needs_bias"]["social"] == 0.2
    assert signal["needs_bias"]["curiosity"] == 0.12
    assert signal["confidence"] == 0.8
    assert signal["safety_flags"] == []


def test_risky_vlm_context_adds_safety_bias_without_activation():
    adapter = VisionContextToAutonomyAdapter()
    signal = adapter.translate(
        {
            "kind": "vlm_semantic_context",
            "caption": "object close to robot",
            "risk": "obstacle close",
            "confidence": 0.9,
        },
        now=3.0,
    ).as_dict()

    assert signal["activation_started"] is False
    assert signal["needs_bias"]["safety"] == 0.6
    assert signal["safety_flags"] == ["vision_risk:obstacle close"]
    assert "prefer_safe_observation" in signal["goal_hints"]


def test_vision_context_to_autonomy_source_has_no_capture_network_or_inference_start():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_import_roots = {"cv2", "requests", "httpx", "ollama"}
    imports = []
    calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                if root in forbidden_import_roots:
                    imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0].lower()
            if root in forbidden_import_roots:
                imports.append((node.module, node.lineno))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {"VideoCapture"}:
                    calls.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                root = _root_name(node.func.value)
                attr = node.func.attr
                if root == "cv2" and attr == "VideoCapture":
                    calls.append((f"{root}.{attr}", node.lineno))
                if root in {"requests", "httpx"} and attr in {"get", "post", "request", "send"}:
                    calls.append((f"{root}.{attr}", node.lineno))
                if root == "ollama" and attr in {"generate", "chat"}:
                    calls.append((f"{root}.{attr}", node.lineno))

    assert imports == []
    assert calls == []

    for endpoint in ["/camera/start", "/camera/snap", "/camera/video", "/vlm/analyze", "/vlm/caption"]:
        assert endpoint not in source
