from __future__ import annotations

import time
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.camera.api.router import get_router
from modules.camera.services.imx500_runner import Imx500Config, Imx500Runner
from modules.camera.services.onsensor_bus import OnSensorDetection, OnSensorEventBus, OnSensorSnapshot


class _Cap:
    gave_up = False

    def __init__(self, has_frame: bool = False):
        self.has_frame = has_frame

    async def snapshot(self):
        return b"jpg" if self.has_frame else None

    def status(self):
        return {
            "backend": "opencv",
            "source": "0",
            "running": self.has_frame,
            "gave_up": False,
            "has_frame": self.has_frame,
            "opencv": {"available": True},
            "picamera2": {"available": False, "import_error": "missing"},
        }

    def mjpeg_generator(self, fps):
        yield b""

    def start(self):
        pass

    def stop(self):
        pass


def test_camera_status_disabled_exposes_truth():
    app = FastAPI()
    app.include_router(get_router(_Cap(False), 15, enabled=False), prefix="/camera")
    client = TestClient(app)
    body = client.get("/camera/status").json()
    assert body["enabled"] is False
    assert body["ok"] is False
    assert body["imx500"]["reason"] == "not_configured"


def test_camera_status_includes_onsensor_and_imx_runner():
    bus = OnSensorEventBus()
    bus.publish(
        OnSensorSnapshot(
            ts=time.time(),
            frame_id=7,
            detections=[OnSensorDetection(class_id=0, label="person", score=0.91, bbox_xyxy_norm=(0.1, 0.1, 0.4, 0.7))],
        )
    )
    runner = Imx500Runner(Imx500Config(enabled=False), bus=bus)
    app = FastAPI()
    app.include_router(get_router(_Cap(True), 15, enabled=True, imx500_runner=runner, onsensor_bus=bus), prefix="/camera")
    client = TestClient(app)
    status = client.get("/camera/status").json()
    assert status["ok"] is True
    assert status["imx500"]["reason"] == "disabled"
    assert status["onsensor"]["has_latest"] is True
    latest = client.get("/camera/onsensor/latest").json()
    assert latest["ok"] is True
    assert latest["snapshot"]["frame_id"] == 7


def test_imx500_status_model_missing_when_library_present(monkeypatch, tmp_path):
    from modules.camera.services import imx500_runner as mod

    monkeypatch.setattr(mod, "IMX500_AVAILABLE", True)
    cfg = Imx500Config(enabled=True, model_path=str(tmp_path / "missing.rpk"))
    runner = Imx500Runner(cfg, bus=OnSensorEventBus())
    data = runner.status()
    assert data["enabled"] is True
    assert data["model_exists"] is False
    assert data["reason"] == "model_missing"
