from __future__ import annotations

import ast
from pathlib import Path

from modules.camera.api import router as camera_router
from modules.camera.services import capture as camera_capture


ROOT = Path(__file__).resolve().parents[3]
ROUTER_SOURCE = ROOT / "modules/camera/api/router.py"
CAPTURE_SOURCE = ROOT / "modules/camera/services/capture.py"


def _has_route(source: str, method: str, path: str) -> bool:
    # Accept both common local variable names:
    #   @r.post("/start")
    #   @router.post("/start")
    needle_double = f'.{method}("{path}")'
    needle_single = f".{method}('{path}')"
    return needle_double in source or needle_single in source


def test_camera_reversible_start_stop_markers_are_exported():
    assert camera_router.CAMERA_REVERSIBLE_START_STOP_CONTRACT is True
    assert camera_router.CAMERA_REVERSIBLE_START_STOP_ROLE == "explicit_route_control_surface"
    assert camera_router.CAMERA_START_STOP_STATUS_ONLY_AUDIT_SAFE is True

    assert camera_capture.CAMERA_CAPTURE_LAZY_OPEN_CONTRACT is True
    assert camera_capture.CAMERA_CAPTURE_IMPORT_STARTS_DEVICE is False
    assert camera_capture.CAMERA_START_STOP_REQUIRES_EXPLICIT_ROUTE_CALL is True


def test_camera_control_routes_exist_as_explicit_reversible_surface():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert _has_route(source, "post", "/start")
    assert _has_route(source, "post", "/stop")
    assert _has_route(source, "get", "/status")
    assert _has_route(source, "get", "/healthz")


def test_camera_router_import_does_not_open_camera_or_capture_frame():
    tree = ast.parse(ROUTER_SOURCE.read_text(encoding="utf-8"))
    forbidden_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in {"VideoCapture", "imread"}:
            forbidden_calls.append((name, node.lineno))
    assert forbidden_calls == []


def test_camera_capture_has_no_top_level_device_open():
    tree = ast.parse(CAPTURE_SOURCE.read_text(encoding="utf-8"))
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
        if name in {"VideoCapture", "start", "open"}:
            forbidden_top_level.append((name, node.lineno))
    assert forbidden_top_level == []
