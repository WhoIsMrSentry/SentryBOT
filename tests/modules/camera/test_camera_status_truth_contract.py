from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.camera.api import router as camera_router
from modules.camera.api.router import get_router
from modules.camera.services import capture as camera_capture


ROOT = Path(__file__).resolve().parents[3]
ROUTER_SOURCE = ROOT / "modules/camera/api/router.py"
CAPTURE_SOURCE = ROOT / "modules/camera/services/capture.py"


class FakeCapture:
    gave_up = False

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.status_calls = 0

    def status(self):
        self.status_calls += 1
        return {
            "running": False,
            "has_frame": False,
            "device": "/dev/video0",
            "backend": "V4L2",
            "gave_up": False,
        }

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


def _nested_status_payload(data: dict) -> dict:
    """Return the capture status payload across supported router schemas.

    Existing router versions may expose capture state at top level or under a
    nested key such as `capture`, `camera`, `status`, or `capture_status`.
    The contract is not the exact JSON shape; it is that status reads do not
    start capture and still surface capture truth when present.
    """

    for key in ("capture", "camera", "status", "capture_status"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def test_camera_status_truth_markers_are_exported():
    assert camera_router.CAMERA_STATUS_TRUTH_CONTRACT is True
    assert camera_router.CAMERA_STATUS_TRUTH_ROLE == "non_activating_camera_runtime_status_surface"
    assert camera_router.CAMERA_STATUS_DOES_NOT_START_CAPTURE is True

    assert camera_capture.CAMERA_CAPTURE_STATUS_TRUTH_CONTRACT is True
    assert camera_capture.CAMERA_CAPTURE_STATUS_ROLE == "capture_state_truth_provider"
    assert camera_capture.CAMERA_CAPTURE_STATUS_DOES_NOT_OPEN_DEVICE is True


def test_camera_status_route_reads_status_without_starting_capture():
    fake = FakeCapture()
    app = FastAPI()
    app.include_router(get_router(fake, 30, enabled=False, imx500_runner=None))

    data = TestClient(app).get("/status").json()
    capture_status = _nested_status_payload(data)

    assert fake.status_calls == 1
    assert fake.start_calls == 0
    assert fake.stop_calls == 0
    assert data["enabled"] is False

    # Router schemas may nest the capture state, but when the capture state is
    # surfaced it must reflect the fake status without activating capture.
    assert capture_status.get("running", False) is False
    assert capture_status.get("has_frame", False) is False
    if "device" in capture_status:
        assert capture_status["device"] == "/dev/video0"


def test_camera_status_and_healthz_routes_are_get_only_truth_surfaces():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert '.get("/status")' in source or ".get('/status')" in source
    assert '.get("/healthz")' in source or ".get('/healthz')" in source


def test_camera_status_truth_contract_does_not_add_import_time_capture():
    for path in [ROUTER_SOURCE, CAPTURE_SOURCE]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden_top_level = []
        for node in tree.body:
            value = None
            if isinstance(node, ast.Expr):
                value = node.value
            elif isinstance(node, ast.Assign):
                value = node.value
            if not isinstance(value, ast.Call):
                continue
            name = ""
            if isinstance(value.func, ast.Name):
                name = value.func.id
            elif isinstance(value.func, ast.Attribute):
                name = value.func.attr
            if name in {"VideoCapture", "start", "open", "read", "snapshot"}:
                forbidden_top_level.append((path.name, name, node.lineno))
        assert forbidden_top_level == []
