from __future__ import annotations

import json
from pathlib import Path


DOC_PATH = Path("OPENCV5_CAMERA_VLM_RESEARCH_NOTE.md")
JSON_PATH = Path("opencv5_camera_vlm_research_note.json")


def _data() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def test_opencv5_research_note_exists_and_is_research_only():
    assert DOC_PATH.exists()
    assert JSON_PATH.exists()

    data = _data()
    assert data["research_only"] is True
    assert data["activation_allowed_now"] is False
    assert data["safety"]["camera_started"] is False
    assert data["safety"]["frame_captured"] is False
    assert data["safety"]["vlm_inference_started"] is False
    assert data["safety"]["hardware_enabled"] is False


def test_opencv5_research_note_locks_project_decisions():
    decisions = _data()["project_decisions"]

    assert decisions["preferred_package_family"] == "opencv-python-headless"
    assert decisions["single_cv2_namespace_package_required"] is True
    assert decisions["preferred_capture_backend"] == "Linux V4L2"
    assert decisions["local_lightweight_vision_model_format"] == "ONNX"
    assert decisions["vlm_policy"] == "keep_remote_or_budget_gated_opencv5_vlm_tbd_not_enough"
    assert decisions["video_capture_property_rule"] == "unsupported_if_value_lt_0_not_value_eq_0"
    assert decisions["do_not_change_pipeline_based_only_on_cv2_version"] is True


def test_opencv5_research_note_records_ai_relevant_findings():
    findings = _data()["findings"]

    assert findings["dnn_new_default_engine"] is True
    assert findings["dnn_new_engine_cpu_only"] is True
    assert findings["onnx_call_site_mostly_unchanged"] is True
    assert findings["darknet_caffe_parsers_removed"] is True
    assert findings["vlm_migration_section_tbd"] is True
    assert findings["facedetectoryn_yunet_preferred_for_new_face_detection"] is True
    assert findings["videocapture_get_unsupported_negative"] is True


def test_opencv5_research_note_has_no_runtime_activation_command_surface():
    text = DOC_PATH.read_text(encoding="utf-8")
    forbidden_runtime_commands = [
        "/camera/start",
        "/camera/snap",
        "/camera/video",
        "/vlm/analyze",
        "/vlm/caption",
        "cv2.VideoCapture(",
        "cv2.imshow(",
        "hardware_enabled=True",
        "camera_started=True",
        "vlm_inference_started=True",
    ]

    for token in forbidden_runtime_commands:
        assert token not in text
