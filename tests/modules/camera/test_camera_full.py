"""Comprehensive tests for camera module: lazy JPEG, subscribers, bridge EOF, lifespan, routes, tracker."""
from __future__ import annotations

import io
import struct
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np

from modules.camera import device_manager as dm_mod
from modules.camera.api.router import get_router
from modules.camera.device_manager import CameraDeviceManager, CameraMode
from modules.camera.services import capture as capture_mod
from modules.camera.services import capture_loops
from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher
from modules.camera.services.imx500_runner import Imx500Config, Imx500Runner
from modules.camera.services.onsensor_bus import OnSensorDetection, OnSensorEventBus, OnSensorSnapshot
from modules.camera.services.tracking import DetectionTracker


def test_frame_publisher_lazy_encode_and_subscriber_condition(monkeypatch):
    pub = FramePublisher()
    encode_calls = []

    if capture_mod.cv2 is not None:
        orig_imencode = capture_mod.cv2.imencode

        def tracked_imencode(*args, **kwargs):
            encode_calls.append(1)
            return orig_imencode(*args, **kwargs)

        monkeypatch.setattr(capture_mod.cv2, "imencode", tracked_imencode)

    raw = np.zeros((16, 16, 3), dtype=np.uint8)
    pub.set_raw_frame(raw, quality=75)

    # Zero idle imencode calls when nobody calls get_jpeg()
    assert encode_calls == []
    st = pub.status()
    assert st["has_frame"] is True
    assert st["frame_count"] == 1
    assert st["subscribers"] == 0

    with pub.subscriber_session():
        assert pub.subscriber_count == 1
        if capture_mod.cv2 is not None:
            jpg = pub.get_jpeg()
            assert jpg is not None and jpg.startswith(b"\xff\xd8")
            assert len(encode_calls) == 1
            # Cached on repeat call for same frame
            assert pub.get_jpeg() == jpg
            assert len(encode_calls) == 1

    assert pub.subscriber_count == 0


def test_frame_publisher_wait_for_frame_wakes_immediately():
    pub = FramePublisher()
    stop = threading.Event()
    result = {}

    def waiter():
        cnt, data = pub.wait_for_frame(after_count=0, timeout=2.0, stop_event=stop)
        result["cnt"] = cnt
        result["data"] = data

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.03)
    pub.set_jpeg(b"\xff\xd8FRAME\xff\xd9")
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert result["cnt"] == 1
    assert result["data"] == b"\xff\xd8FRAME\xff\xd9"


def test_bridge_loop_exits_on_eof_and_rejects_oversized_frame():
    pub = FramePublisher()
    cap = CameraCapture(CaptureConfig(), pub)

    # Valid frame followed by EOF
    payload = b"\xff\xd8OK\xff\xd9"
    cap._proc = SimpleNamespace(
        stdout=io.BytesIO(struct.pack(">I", len(payload)) + payload),
        poll=lambda: 1,
    )
    cap._bridge_capture_loop()
    assert pub.get_jpeg() == payload
    assert "EOF" in cap._last_error

    # Oversized frame header (> MAX_BRIDGE_FRAME_BYTES) must abort safely without MemoryError
    cap._proc = SimpleNamespace(
        stdout=io.BytesIO(struct.pack(">I", 0x7FFFFFFF) + b"garbage"),
        poll=lambda: None,
    )
    cap._bridge_capture_loop()
    assert "invalid bridge frame size" in cap._last_error


def test_apply_frame_flip_safe_when_cv2_missing(monkeypatch):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    monkeypatch.setattr(capture_loops, "cv2", None)
    assert capture_loops.apply_frame_flip(frame, "90") is frame
    assert capture_loops.apply_frame_flip(frame, "270") is frame


def test_create_app_lifespan_config_binding_and_disabled_imx(monkeypatch):
    from modules.camera import xCameraService as svc_mod

    captured_cfg = {}
    stopped = []

    class _FakeCap:
        picam = None
        gave_up = False

        def __init__(self, cfg, pub):
            captured_cfg["cfg"] = cfg
            self.pub = pub

        def start(self):
            return False

        def stop(self):
            stopped.append("capture")

        def status(self):
            return {"running": False, "has_frame": False, "gave_up": False}

        async def snapshot(self):
            return None

    class _FakeRunner:
        camera_num = 0
        prep_calls = 0

        def __init__(self, cfg, bus=None):
            self.cfg = cfg

        def prepare(self):
            _FakeRunner.prep_calls += 1
            return False

        def attach_camera(self, *a):
            pass

        def start(self):
            return False

        def stop(self):
            stopped.append("runner")

        def status(self):
            return {"enabled": False, "available": False, "running": False, "reason": "disabled"}

    monkeypatch.setattr(svc_mod, "CameraCapture", _FakeCap)
    monkeypatch.setattr(svc_mod, "Imx500Runner", _FakeRunner)
    monkeypatch.setattr(
        svc_mod,
        "load_config",
        lambda *a, **k: {
            "enabled": False,
            "backend": "opencv_v4l2",
            "source": "/dev/video2",
            "resolution": {"width": 640, "height": 480},
            "fps_target": 18,
            "picamera2": {"size": {"width": 1280, "height": 720}, "frame_rate": 30},
            "imx500": {"enabled": False},
        },
    )

    app = svc_mod.create_app()
    assert _FakeRunner.prep_calls == 0  # enabled=False never calls runner.prepare()
    cfg = captured_cfg["cfg"]
    assert cfg.backend == "opencv_v4l2"
    assert cfg.source == "/dev/video2"
    assert cfg.size == (640, 480)
    assert cfg.target_fps == 18

    with TestClient(app) as client:
        assert client.get("/status").status_code == 200
    assert stopped == ["runner", "capture"]


def test_camera_router_snap_video_and_tracking_routes():
    pub = FramePublisher()
    cap = CameraCapture(CaptureConfig(frame_rate=20), pub)
    bus = OnSensorEventBus()
    bus.publish(
        OnSensorSnapshot(
            ts=time.time(),
            frame_id=3,
            detections=[OnSensorDetection(class_id=0, label="person", score=0.95, bbox_xyxy_norm=(0.2, 0.2, 0.5, 0.7))],
        )
    )
    runner = Imx500Runner(Imx500Config(enabled=False), bus=bus)
    runner.tracker.update(bus.latest().detections)

    app = FastAPI()
    app.include_router(get_router(cap, 20, enabled=True, imx500_runner=runner, onsensor_bus=bus), prefix="/camera")
    client = TestClient(app)

    # Empty buffer -> /snap 503
    assert client.get("/camera/snap").status_code == 503
    pub.set_jpeg(b"\xff\xd8SNAP\xff\xd9")
    snap_resp = client.get("/camera/snap")
    assert snap_resp.status_code == 200
    assert snap_resp.content == b"\xff\xd8SNAP\xff\xd9"

    # Tracking & onsensor endpoints
    assert client.get("/camera/onsensor/latest").json()["snapshot"]["frame_id"] == 3
    assert client.get("/camera/tracking/tracks").json()["count"] == 1
    assert client.get("/camera/tracking/target").json()["ok"] is True
    assert client.post("/camera/tracking/select", json={"label": "person", "strategy": "center"}).json()["ok"] is True
    assert client.post("/camera/tracking/select", json={"label": "person", "strategy": "bad"}).status_code == 422

    # mjpeg_generator yields new frame and exits cleanly when capture stops
    import asyncio

    async def _collect():
        pub2 = FramePublisher()
        cap2 = CameraCapture(CaptureConfig(), pub2)
        cap2._thread = SimpleNamespace(is_alive=lambda: True)  # simulated running thread
        chunks = []

        async def _push():
            await asyncio.sleep(0.02)
            pub2.set_jpeg(b"\xff\xd8ONE\xff\xd9")
            await asyncio.sleep(0.03)
            cap2._stop.set()
            pub2.wake_all()

        task = asyncio.create_task(_push())
        async for chunk in cap2.mjpeg_generator(30):
            chunks.append(chunk)
        await task
        return chunks, pub2.subscriber_count

    chunks, remaining_subs = asyncio.run(_collect())
    assert len(chunks) == 1
    assert b"\xff\xd8ONE\xff\xd9" in chunks[0]
    assert remaining_subs == 0


def test_camera_device_manager_acquire_switch_and_shutdown():
    orig = dm_mod.CameraDeviceManager._instance
    dm_mod.CameraDeviceManager._instance = None
    try:
        mgr = CameraDeviceManager.get_instance()
        h1 = mgr.acquire("consumer_a", CameraMode.LOCAL)
        assert mgr.get_mode() == CameraMode.LOCAL
        # Releasing consumer_a and reacquiring consumer_b in REMOTE calls switch_mode cleanly (no AttributeError)
        h1.release()
        h2 = mgr.acquire("consumer_b", CameraMode.REMOTE)
        assert mgr.get_mode() == CameraMode.REMOTE

        bound_cap = MagicMock()
        mgr.attach_capture(bound_cap)
        mgr.shutdown()
        assert mgr.has_reference("consumer_b") is False
        bound_cap.stop.assert_called_once()
        assert h2.release() is False
    finally:
        dm_mod.CameraDeviceManager._instance = orig


def test_imx500_runner_unpack_bounds_and_tracker_selection_lock():
    runner = Imx500Runner(Imx500Config(enabled=False), bus=OnSensorEventBus())
    assert runner._unpack([]) == ([], [], [])
    assert runner._unpack([np.empty((0, 4)), np.empty((0,)), np.empty((0,))]) == ([], [], [])
    assert runner._unpack([[[1, 2, 3]]]) == ([], [], [])  # len < 3 safely handled

    tracker = DetectionTracker()
    tracker.select("cat", "confidence", track_id=2)
    sel = tracker.selection()
    assert sel == {"label": "cat", "strategy": "confidence", "track_id": 2}
