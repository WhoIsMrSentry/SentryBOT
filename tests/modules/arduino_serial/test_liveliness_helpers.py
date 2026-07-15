"""Service-level liveliness helpers send valid contract payloads."""

from __future__ import annotations

import json

from .fake_transport_sim import FakeTransportSim
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


def _svc():
    transport = FakeTransportSim()
    svc = xArduinoSerialService(
        config_overrides={"transport": "serial", "auto_heartbeat": False},
        transport_factory=lambda *a, **k: transport,
    )
    svc.start()
    return svc, transport


def _liveliness_frames(transport):
    frames = []
    for line in transport._buf.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("cmd") == "liveliness":
            frames.append(obj)
    return frames


def test_liveliness_start_sends_enable_true():
    svc, transport = _svc()
    try:
        resp = svc.liveliness_start(mode="breathe", amplitude_deg=6, period_ms=4000)
        assert resp.get("ok") is True
        frames = _liveliness_frames(transport)
        assert frames and frames[0]["enable"] is True
        assert frames[0]["mode"] == "breathe"
    finally:
        svc.stop()


def test_liveliness_stop_sends_enable_false():
    svc, transport = _svc()
    try:
        resp = svc.liveliness_stop()
        assert resp.get("ok") is True
        frames = _liveliness_frames(transport)
        assert frames and frames[0]["enable"] is False
    finally:
        svc.stop()
