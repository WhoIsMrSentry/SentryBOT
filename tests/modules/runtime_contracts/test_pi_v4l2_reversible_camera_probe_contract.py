from __future__ import annotations

import ast
from pathlib import Path

from tools.pi_v4l2_reversible_camera_probe import (
    V4L2_REVERSIBLE_CAMERA_PROBE_CONTRACT,
    V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_ALLOWS_CAMERA_OPEN,
    V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_STATUS_ONLY_SAFE,
    V4L2_REVERSIBLE_CAMERA_PROBE_ROLE,
    build_report,
    discover_video_devices,
    probe_device_reversible,
)


class FakeCapture:
    def __init__(self, device, backend):
        self.device = device
        self.backend = backend
        self.released = False

    def isOpened(self):
        return True

    def release(self):
        self.released = True


class FakeCv2:
    CAP_V4L2 = 200

    def __init__(self):
        self.created = []

    def VideoCapture(self, device, backend):
        cap = FakeCapture(device, backend)
        self.created.append(cap)
        return cap


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def test_v4l2_reversible_camera_probe_contract_markers():
    assert V4L2_REVERSIBLE_CAMERA_PROBE_CONTRACT is True
    assert V4L2_REVERSIBLE_CAMERA_PROBE_ROLE == "explicit_opt_in_reversible_v4l2_probe"
    assert V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_STATUS_ONLY_SAFE is True
    assert V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_ALLOWS_CAMERA_OPEN is False


def test_discover_video_devices_from_fake_dev_root(tmp_path):
    (tmp_path / "video0").write_text("", encoding="utf-8")
    (tmp_path / "video2").write_text("", encoding="utf-8")
    (tmp_path / "notvideo").write_text("", encoding="utf-8")

    assert discover_video_devices(tmp_path) == [str(tmp_path / "video0"), str(tmp_path / "video2")]


def test_default_probe_does_not_open_camera():
    decision = probe_device_reversible("/dev/video0", allow_camera_open=False)

    assert decision.camera_open_attempted is False
    assert decision.camera_opened is False
    assert decision.released is False
    assert decision.frame_captured is False
    assert decision.reason == "camera_open_not_allowed_default_status_only"


def test_explicit_opt_in_probe_opens_and_releases_without_frame_read():
    fake = FakeCv2()
    decision = probe_device_reversible("/dev/video0", allow_camera_open=True, cv2_module=fake)

    assert decision.camera_open_attempted is True
    assert decision.camera_opened is True
    assert decision.released is True
    assert decision.frame_captured is False
    assert fake.created[0].released is True


def test_report_default_is_status_only_even_when_device_exists(tmp_path):
    (tmp_path / "video0").write_text("", encoding="utf-8")
    report = build_report(allow_camera_open=False, target_pi=True, dev_root=tmp_path)

    assert report["overall_ok"] is True
    assert report["activation_allowed_now"] is False
    assert report["target"]["target_pi"] is True
    assert report["probe"]["camera_open_attempted"] is False
    assert report["probe"]["frame_captured"] is False
    assert report["safety"]["hardware_enabled"] is False


def test_tool_source_has_no_frame_read_or_runtime_endpoint_call():
    source = Path("tools/pi_v4l2_reversible_camera_probe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            root = _root_name(node.func.value)
            attr = node.func.attr
            if root in {"requests", "httpx", "ollama"} and attr in {"get", "post", "request", "send", "generate", "chat"}:
                forbidden_calls.append((f"{root}.{attr}", node.lineno))
            if attr in {"read", "imshow"}:
                forbidden_calls.append((attr, node.lineno))
    assert forbidden_calls == []

    for endpoint in ["/camera/start", "/camera/snap", "/camera/video", "/vlm/analyze", "/vlm/caption"]:
        assert endpoint not in source
