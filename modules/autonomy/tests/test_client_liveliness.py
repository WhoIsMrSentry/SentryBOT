"""Autonomy ServiceClient liveliness wiring builds a valid contract payload."""

from __future__ import annotations

from modules.arduino_serial.contract import validate_arduino_payload
from modules.autonomy.services.client import ServiceClient


def _client():
    c = ServiceClient.__new__(ServiceClient)
    captured = {}

    def _fake_request(payload):
        captured["payload"] = payload
        return {"ok": True}

    c._arduino_request = _fake_request  # type: ignore
    return c, captured


def test_set_liveliness_enable_builds_valid_payload():
    c, captured = _client()
    c.set_liveliness(True, mode="breathe", amplitude_deg=5, period_ms=3000)
    payload = captured["payload"]
    assert payload["cmd"] == "liveliness"
    assert payload["enable"] is True
    assert validate_arduino_payload(payload) is None


def test_set_liveliness_disable_builds_valid_payload():
    c, captured = _client()
    c.set_liveliness(False)
    payload = captured["payload"]
    assert payload["enable"] is False
    assert validate_arduino_payload(payload) is None
