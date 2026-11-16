"""Comprehensive unit & API tests for modules/expression/piservo."""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from modules.expression.piservo.config_loader import load_config
from modules.expression.piservo.services.driver import Servo, ServoConfig, _ArduinoWrapper, _SimGPIO
from modules.expression.piservo.services.runner import EarRunner
from modules.expression.piservo.xPiServoService import create_app


def _make_runner(**kwargs) -> EarRunner:
    shared = _SimGPIO()
    left = ServoConfig(gpio=12, min_us=500, max_us=2500, center_deg=90.0)
    right = ServoConfig(gpio=13, min_us=500, max_us=2500, center_deg=90.0)
    return EarRunner(left_cfg=left, right_cfg=right, shared_backend=shared, **kwargs)


def test_piservo_router_validation_and_endpoints():
    runner = _make_runner(smooth_enabled=False, idle_detach_ms=0)
    try:
        from fastapi import FastAPI
        from modules.expression.piservo.api.router import get_router

        app = FastAPI()
        app.include_router(get_router(runner))
        client = TestClient(app)

        hz = client.get("/piservo/healthz")
        assert hz.status_code == 200
        assert hz.json()["ok"] is True
        assert hz.json()["backend"] == "sim"

        # Invalid angles return 400 (never HTTP 500)
        assert client.post("/piservo/set", params={"left": -5, "right": 90}).status_code == 400
        assert client.post("/piservo/set", params={"left": 181, "right": 90}).status_code == 400
        assert client.post("/piservo/set", params={"left": "nan", "right": 90}).status_code == 400

        # Valid emotion (query & JSON body)
        r_emo_q = client.post("/piservo/emotion", params={"name": "joy"})
        assert r_emo_q.status_code == 200 and r_emo_q.json()["left"] == 70.0
        r_emo_j = client.post("/piservo/emotion", json={"name": "curious"})
        assert r_emo_j.status_code == 200 and r_emo_j.json()["ok"] is True
        assert client.post("/piservo/emotion", params={"name": "   "}).status_code == 400

        # Valid & invalid gestures
        for valid_g in ("wakeword", "sound", "vigilance", "relax", "idle"):
            assert client.post("/piservo/gesture", params={"name": valid_g}).status_code == 200
        assert client.post("/piservo/gesture", params={"name": "unknown_xyz"}).status_code == 400

        # Valid & invalid events
        assert client.post("/piservo/event", params={"kind": "doa:-45"}).status_code == 200
        assert client.post("/piservo/event", params={"kind": "sound:30"}).status_code == 200
        assert client.post("/piservo/event", params={"kind": "doa:bad"}).status_code == 400
        assert client.post("/piservo/event", params={"kind": "nope"}).status_code == 400

        # Reflex validation & cooldown angle preservation
        assert client.post("/piservo/reflex", params={"angle": "nan"}).status_code == 400
        assert client.post("/piservo/reflex", params={"angle": 0, "energy": -1}).status_code == 400
    finally:
        runner.close()


def test_piservo_reflex_cooldown_preserves_target_angles():
    runner = _make_runner(smooth_enabled=False, idle_detach_ms=0)
    try:
        l1, r1 = runner.reflex(-50.0, energy=1.0)
        assert l1 < 90.0
        # Immediate second call inside cooldown must NOT snap ears back to 90.0
        l2, r2 = runner.reflex(50.0, energy=1.0)
        assert (l2, r2) == (l1, r1)
    finally:
        runner.close()


def test_piservo_shared_backend_smooth_ramp_idle_detach_and_lifespan():
    shared = _SimGPIO()
    left = ServoConfig(gpio=12, center_deg=85.0)
    right = ServoConfig(gpio=13, center_deg=95.0)
    runner = EarRunner(
        left_cfg=left,
        right_cfg=right,
        shared_backend=shared,
        smooth_enabled=True,
        ramp_hz=100.0,
        max_speed_deg_s=500.0,
        idle_detach_ms=60,
    )
    try:
        assert runner.left._io is runner.right._io
        runner.set_angles(135.0, 55.0)
        # Wait for ramp to settle and idle detach to cut PWM to 0
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and (runner.left.pwm_active or runner.right.pwm_active):
            time.sleep(0.02)
        assert shared.pulses[12] == 0
        assert shared.pulses[13] == 0
        st = runner.status()
        assert st["left"] == 135.0 and st["right"] == 55.0
        assert st["pwm_active"] is False
    finally:
        runner.close()
    assert shared.closed is True

    # Lifespan shutdown test via TestClient context manager
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/piservo/status")
        assert r.status_code == 200
        assert r.json()["ok"] is True
    assert app.state.ear_runner.is_healthy() is False


def test_piservo_config_invalid_port_and_arduino_wrapper_bounds(monkeypatch, caplog):
    monkeypatch.setenv("PISERVO_PORT", "not_a_port")
    with caplog.at_level(logging.WARNING):
        cfg = load_config()
    assert cfg["server"]["port"] == 8093

    monkeypatch.setenv("PISERVO_PORT", "99999")
    cfg2 = load_config()
    assert cfg2["server"]["port"] == 8093

    calls = []

    class StubSvc:
        def set_servo(self, idx, deg, wait_ack=True):
            calls.append((idx, round(deg, 2), wait_ack))

    drv_stub = SimpleNamespace(svc=StubSvc())
    custom_cfg = ServoConfig(gpio=2, min_us=1000, max_us=2000, min_deg=0.0, max_deg=180.0, arduino_index=2)
    wrapper = _ArduinoWrapper(index=2, cfg=custom_cfg, driver=drv_stub)
    servo = Servo(custom_cfg, backend=wrapper)
    servo.set_angle(90.0)
    assert calls == [(2, 90.0, False)]
