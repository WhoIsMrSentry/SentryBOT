"""Comprehensive unit & API tests for modules/expression and modules/expression/animate."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.expression.animate.api.router import get_router
from modules.expression.animate.xAnimateService import xAnimateService
from modules.expression.config_loader import load_config as load_expr_root_config
from modules.expression.semantic.config_loader import load_config as load_semantic_config


class FakeSerial:
    def __init__(self):
        self.sent = []
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def set_pose(self, pose, duration_ms=None, source="autonomy"):
        self.sent.append({"cmd": "set_pose", "pose": list(pose), "duration_ms": duration_ms})

    def set_servo(self, index, deg, source="autonomy"):
        self.sent.append({"cmd": "set_servo", "index": index, "deg": deg})


def test_expression_single_source_of_truth_config():
    repo_root = Path(__file__).resolve().parents[4]
    assert not (repo_root / "modules" / "expression" / "config" / "config.yml").exists()
    assert load_expr_root_config() == load_semantic_config()


def test_animate_router_list_validation_status_and_return_to_rest():
    serial = FakeSerial()
    ears = MagicMock()
    svc = xAnimateService(
        serial=serial,
        config_overrides={"rest_pose": [90, 92, 85, 95], "interpolate": True},
        ears=ears,
    )
    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    r_list = client.get("/animate/list")
    assert r_list.status_code == 200
    assert "sit" in r_list.json()["animations"]

    # Path traversal & invalid speed -> 400; missing animation -> 404
    assert client.post("/animate/run", params={"name": "../secret"}).status_code == 400
    assert client.post("/animate/run", params={"name": "sub/sit"}).status_code == 400
    assert client.post("/animate/run", params={"name": "sit", "speed": 0}).status_code == 400
    assert client.post("/animate/run", params={"name": "sit", "speed": "nan"}).status_code == 400
    assert client.post("/animate/run", params={"name": "does_not_exist"}).status_code == 404

    # Asynchronous loop playback + GET /animate/status diagnostics + return_to_rest
    r_run = client.post("/animate/run", params={"name": "sit", "speed": 4.0, "loop": "true"})
    assert r_run.status_code == 200
    assert r_run.json()["status"] == "running"

    r_status = client.get("/animate/status")
    assert r_status.status_code == 200
    st = r_status.json()
    assert st["running"] is True
    assert st["name"] == "sit"
    assert st["loop"] is True
    assert st["total_steps"] == 2

    r_stop = client.post("/animate/stop", params={"return_to_rest": "true"})
    assert r_stop.status_code == 200
    assert r_stop.json()["return_to_rest"] is True

    r_after = client.get("/animate/status")
    assert r_after.json()["running"] is False
    # Final pose restored servos and ears to rest_pose
    assert serial.sent[-1]["cmd"] == "set_pose"
    assert serial.sent[-1]["pose"] == [90, 92, 85, 95]
    ears.set_angles.assert_called_with(85.0, 95.0)


def test_animate_concurrency_null_steps_ears_error_and_procedural_idle(monkeypatch):
    serial = FakeSerial()
    broken_ears = MagicMock()
    broken_ears.set_angles.side_effect = RuntimeError("gpio glitch")
    svc = xAnimateService(serial=serial, ears=broken_ears)

    null_anim = {
        "name": "null_fields",
        "loop": False,
        "steps": [
            {"pose": [95, 85, 80, 100], "duration_ms": None, "hold_ms": None},
        ],
    }
    long_anim = {
        "name": "long",
        "loop": True,
        "steps": [
            {"pose": [90, 90, 90, 90], "duration_ms": 200, "hold_ms": 200},
        ],
    }

    def fake_load(name):
        return long_anim if name == "long" else null_anim

    monkeypatch.setattr(svc, "load", fake_load)

    # Null duration/hold and failing ears hook do not crash playback
    assert svc.run("null_fields", loop=False) is True

    # Starting a new run safely interrupts a running background loop instead of interleaving
    svc.start_async("long", loop=True)
    time.sleep(0.05)
    assert svc.status()["running"] is True
    t2 = threading.Thread(target=lambda: svc.run("null_fields", loop=False))
    t2.start()
    t2.join(timeout=2.0)
    assert not t2.is_alive()
    assert svc.status()["running"] is False

    # ProceduralMotionEngine wired cleanly through sample_idle_pose & step_idle
    sample = svc.step_idle(current_time_s=0.0)
    assert "pan" in sample and "tilt" in sample and "ears" in sample


def test_animate_missing_serial_raises_runtime_error(monkeypatch):
    import sys

    anim_mod = sys.modules["modules.expression.animate.xAnimateService"]
    monkeypatch.setattr(anim_mod, "xArduinoSerialService", None)
    try:
        anim_mod.xAnimateService(serial=None)
        assert False, "Expected RuntimeError when xArduinoSerialService is unavailable"
    except RuntimeError as exc:
        assert "xArduinoSerialService" in str(exc)
