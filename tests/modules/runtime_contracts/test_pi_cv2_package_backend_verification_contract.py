from __future__ import annotations

import json
from pathlib import Path

from tools.pi_cv2_package_backend_verification import (
    CV2_PACKAGE_BACKEND_VERIFICATION_CONTRACT,
    CV2_PACKAGE_BACKEND_VERIFICATION_ROLE,
    CV2_PACKAGE_BACKEND_VERIFICATION_STATUS_ONLY_SAFE,
    analyze_cv2_environment,
    detect_v4l2_support,
)


def test_cv2_package_backend_contract_markers():
    assert CV2_PACKAGE_BACKEND_VERIFICATION_CONTRACT is True
    assert CV2_PACKAGE_BACKEND_VERIFICATION_ROLE == "pi_cv2_package_backend_report_only_verifier"
    assert CV2_PACKAGE_BACKEND_VERIFICATION_STATUS_ONLY_SAFE is True


def test_pi_target_accepts_single_headless_package_with_v4l2():
    report = analyze_cv2_environment(
        installed_packages={"opencv-python-headless": "5.0.0.93"},
        cv2_runtime={"cv2_importable": True, "cv2_version": "5.0.0", "v4l2_build_support": True},
        platform_system="Linux",
        platform_machine="aarch64",
    )

    assert report["overall_ok"] is True
    assert report["target"]["target_pi"] is True
    assert report["packages"]["single_cv2_namespace_package"] is True
    assert report["packages"]["headless_package_detected"] is True
    assert report["activation_allowed_now"] is False
    assert report["safety"]["camera_started"] is False
    assert report["safety"]["frame_captured"] is False


def test_pi_target_blocks_multiple_cv2_namespace_packages():
    report = analyze_cv2_environment(
        installed_packages={
            "opencv-python": "5.0.0.93",
            "opencv-python-headless": "5.0.0.93",
        },
        cv2_runtime={"cv2_importable": True, "cv2_version": "5.0.0", "v4l2_build_support": True},
        platform_system="Linux",
        platform_machine="aarch64",
    )

    assert report["overall_ok"] is False
    assert "multiple_cv2_namespace_packages_detected" in report["blockers"]


def test_pi_target_prefers_headless_package():
    report = analyze_cv2_environment(
        installed_packages={"opencv-python": "5.0.0.93"},
        cv2_runtime={"cv2_importable": True, "cv2_version": "5.0.0", "v4l2_build_support": True},
        platform_system="Linux",
        platform_machine="aarch64",
    )

    assert report["overall_ok"] is False
    assert "pi_target_should_use_headless_package" in report["blockers"]


def test_v4l2_detection_and_report_only_output_shape():
    assert detect_v4l2_support("Video I/O:\n    V4L/V4L2: YES") is True
    assert detect_v4l2_support("Video I/O:\n    V4L/V4L2: NO") is False
    assert detect_v4l2_support("no video info") is None

    report = analyze_cv2_environment(
        installed_packages={},
        cv2_runtime={"cv2_importable": False, "cv2_version": None, "v4l2_build_support": None},
        platform_system="Windows",
        platform_machine="AMD64",
    )
    assert report["target"]["target_pi"] is False
    assert report["activation_allowed_now"] is False
    assert report["safety"]["hardware_enabled"] is False


def test_tool_source_has_no_camera_open_or_network_call():
    source = Path("tools/pi_cv2_package_backend_verification.py").read_text(encoding="utf-8")
    forbidden = [
        "VideoCapture(",
        ".read(",
        "/camera/start",
        "/camera/snap",
        "/camera/video",
        "/vlm/analyze",
        "/vlm/caption",
        "requests.",
        "httpx.",
        "ollama.",
        "hardware_enabled=True",
    ]
    for token in forbidden:
        assert token not in source
