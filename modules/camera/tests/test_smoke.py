from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _cv2_importable() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except Exception:
        return False


def test_import():
    if not _cv2_importable():
        pytest.skip("cv2 not installed")
    from modules.camera import xCameraService as cam

    assert hasattr(cam, "create_app") and callable(cam.create_app)


def test_config_loader():
    from modules.camera.config_loader import load_config

    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "enabled" in cfg
    assert cfg.get("enabled") is False


def test_config_loader_cam_enabled_env(monkeypatch):
    from modules.camera.config_loader import load_config

    monkeypatch.setenv("CAM_ENABLED", "false")
    cfg = load_config()
    assert cfg.get("enabled") is False


def test_service_init_without_start(monkeypatch):
    if not _cv2_importable():
        pytest.skip("cv2 not installed")
    from modules.camera.xCameraService import create_app

    started = []

    class _Cap:
        gave_up = False

        def start(self):
            started.append(True)

        def stop(self):
            pass

        async def snapshot(self):
            return None

        def mjpeg_generator(self, fps):
            yield b""

    monkeypatch.setattr("modules.camera.xCameraService.CameraCapture", lambda *a, **k: _Cap())
    monkeypatch.setattr("modules.camera.xCameraService.FramePublisher", lambda: MagicMock())
    monkeypatch.setattr(
        "modules.camera.xCameraService.load_config",
        lambda *a, **k: {"enabled": False, "resolution": {"width": 640, "height": 480}, "opencv": {}},
    )
    app = create_app()
    assert app is not None
    assert started == []


def test_router_disabled_healthz():
    from modules.camera.api.router import get_router

    cap = MagicMock()
    cap.gave_up = False

    async def _snap():
        return None

    cap.snapshot = _snap

    app = FastAPI()
    app.include_router(get_router(cap, 15, enabled=False), prefix="/camera")
    client = TestClient(app)
    resp = client.get("/camera/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["enabled"] is False
    assert body["reason"] == "camera_disabled"


def test_router_start_blocked_when_disabled():
    from modules.camera.api.router import get_router

    cap = MagicMock()
    app = FastAPI()
    app.include_router(get_router(cap, 15, enabled=False), prefix="/camera")
    client = TestClient(app)
    resp = client.post("/camera/start")
    assert resp.status_code == 503
    cap.start.assert_not_called()
