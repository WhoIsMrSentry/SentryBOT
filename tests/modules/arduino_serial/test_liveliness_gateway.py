"""Gateway behavior: /arduino/request validates and dispatches liveliness."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.arduino_serial.api.router import get_router
from modules.arduino_serial.contract import build_liveliness_cmd
from .fake_transport_sim import FakeTransportSim
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


def _client():
    transport = FakeTransportSim()
    svc = xArduinoSerialService(
        config_overrides={"transport": "serial"},
        transport_factory=lambda *a, **k: transport,
    )
    svc.start()
    app = FastAPI()
    app.include_router(get_router(svc))
    return TestClient(app), svc, transport


def test_request_liveliness_enable_round_trips():
    client, svc, transport = _client()
    try:
        payload = build_liveliness_cmd(True, mode="breathe", amplitude_deg=5, period_ms=4000)
        resp = client.post("/arduino/request", json=payload, params={"timeout": 1.0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["resp"].get("ok") is True
        # The fake firmware echoes the command name back.
        assert body["resp"].get("cmd") == "liveliness"
        assert b"liveliness" in transport._buf
    finally:
        svc.stop()


def test_request_rejects_invalid_liveliness_with_400():
    client, svc, _ = _client()
    try:
        # amplitude far out of range -> validator rejects before transport
        resp = client.post("/arduino/request", json={"cmd": "liveliness", "enable": True, "amplitude_deg": 500})
        assert resp.status_code == 400
        assert "amplitude_deg" in resp.json()["detail"]
    finally:
        svc.stop()


def test_send_liveliness_disable_ok():
    client, svc, _ = _client()
    try:
        resp = client.post("/arduino/send", json=build_liveliness_cmd(False))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
    finally:
        svc.stop()
