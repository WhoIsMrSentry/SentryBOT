from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.arduino_serial.api.router import get_router
from modules.arduino_serial.contract import (
    build_ack_cmd,
    build_telemetry_start_cmd,
    validate_arduino_payload,
)
from modules.arduino_serial.head_arbiter_integration import HeadArbiterTransportWrapper
from modules.arduino_serial.services.driver import ArduinoDriver
from modules.arduino_serial.services.safety_watchdog import HardwareSafetyWatchdog
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService
from tests.modules.arduino_serial.fake_transport_sim import FakeTransportSim


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: List[Dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, json: Any = None, params: Any = None, timeout: Any = None):
        self.calls.append({"url": url, "json": json, "params": params, "timeout": timeout})
        return self._handler(url, json, params, timeout)

    def close(self) -> None:
        self.closed = True


def test_esp_http_feeds_watchdog_verifies_seq_and_respects_timeout() -> None:
    def handler(url: str, body: dict, params: Any, timeout: Any):
        if url.endswith("/send"):
            return _FakeResponse(200, {"ok": True})
        if url.endswith("/request"):
            return _FakeResponse(200, {"ok": True, "resp": {"ok": True, "ack_seq": body["seq"]}})
        raise AssertionError(f"unexpected url: {url}")

    svc = xArduinoSerialService(
        config_overrides={
            "transport": "esp_http",
            "esp_base_url": "http://esp.local:8080",
            "request_timeout_ms": 5000,
            "request_max_retries": 0,
            "auto_heartbeat": False,
        }
    )
    sess = _FakeSession(handler)
    svc._esp_http = sess
    assert svc._writer_thread is None
    assert svc.watchdog is not None

    # Force old feed timestamp then send heartbeat -> watchdog must refresh!
    svc.watchdog._last_feed_ts = time.monotonic() - 10.0
    svc.heartbeat()
    assert svc.watchdog.status()["time_since_last_feed_s"] < 1.0

    # Explicit timeout=1.0 MUST NOT be overwritten by request_timeout_ms=5000
    resp = svc.request({"cmd": "hello"}, timeout=1.0)
    assert resp["ok"] is True
    assert sess.calls[-1]["params"]["timeout"] == 1.0

    # Mismatched seq is rejected cleanly in esp_http mode
    svc._esp_http = _FakeSession(
        lambda u, b, p, t: _FakeResponse(200, {"ok": True, "resp": {"ok": True, "ack_seq": 999999}})
    )
    try:
        svc.request({"cmd": "hello", "seq": 5}, timeout=1.0)
        raise AssertionError("expected seq mismatch error")
    except RuntimeError as exc:
        assert "seq mismatch" in str(exc)
    svc.stop()


def test_esp_http_circuit_breaker_and_ack_send() -> None:
    attempts = 0

    def fail_handler(url: str, body: dict, params: Any, timeout: Any):
        nonlocal attempts
        attempts += 1
        raise ConnectionError("esp offline")

    svc = xArduinoSerialService(
        config_overrides={
            "transport": "esp_http",
            "esp_pause_after_failures": 2,
            "esp_pause_sec": 30.0,
            "request_max_retries": 0,
            "auto_heartbeat": False,
            "watchdog": {"enabled": False},
        }
    )
    svc._esp_http = _FakeSession(fail_handler)

    for _ in range(2):
        try:
            svc.send({"cmd": "hb"}, bypass_arbiter=True)
        except ConnectionError:
            pass

    assert attempts == 2
    assert svc._esp_is_paused() is True
    try:
        svc.send({"cmd": "hb"}, bypass_arbiter=True)
        raise AssertionError("expected paused error")
    except RuntimeError as exc:
        assert "paused" in str(exc)
    assert attempts == 2

    # Reset ESP and verify neopixel_request sends ACK via HTTP /send in esp_http mode!
    svc._esp_note_success()
    ok_sess = _FakeSession(lambda u, b, p, t: _FakeResponse(200, {"ok": True}))
    svc._esp_http = ok_sess
    svc._ingest_message({"event": "neopixel_request", "seq": 77})
    assert any(c["url"].endswith("/send") and c["json"] == {"ok": True, "ack_seq": 77} for c in ok_sess.calls)
    assert svc.get_metrics()["acks_sent"] == 1
    svc.stop()


def test_serial_out_of_order_seq_buffering() -> None:
    svc = xArduinoSerialService(
        config_overrides={"transport": "serial", "auto_heartbeat": False, "watchdog": {"enabled": False}},
        transport_factory=lambda *a, **k: FakeTransportSim(),
    )
    svc._ser = FakeTransportSim()
    # Pre-load response for another seq (10) BEFORE our expected seq (20)
    svc._rx_queue.put({"ok": True, "ack_seq": 10, "msg": "earlier"})
    svc._rx_queue.put({"ok": True, "ack_seq": 20, "msg": "target"})

    res = svc._request_locked_serial({"cmd": "get_state", "seq": 20}, timeout=0.5)
    assert res["msg"] == "target"
    assert svc._unmatched_responses[10]["msg"] == "earlier"
    svc.stop()


def test_rfid_authorization_windows_and_normalization() -> None:
    svc = xArduinoSerialService(
        config_overrides={
            "transport": "serial",
            "auto_heartbeat": False,
            "watchdog": {"enabled": False},
            "rfid": {"allowed_uids": ["aa-bb-01"], "authorize_window_s": 1.0},
        }
    )
    assert svc.authorize_rfid()["reason"] == "no_rfid"

    svc._ingest_message({"event": "rfid", "uid": " AA-BB-01 "})
    snap = svc.get_last_rfid()
    assert snap is not None and snap["uid"] == "AA-BB-01"
    assert svc.authorize_rfid()["authorized"] is True
    assert svc.authorize_rfid(uid="FF-00")["reason"] == "unauthorized"

    # Simulate stale RFID read
    svc._last_rfid = ("AA-BB-01", time.time() - 5.0)
    assert svc.authorize_rfid()["reason"] == "stale"
    svc.stop()


def test_head_arbiter_zero_coords_and_fail_closed_plus_driver_atomic_head() -> None:
    seen: list[dict] = []

    class RecordingArbiter:
        def __init__(self, boom: bool = False) -> None:
            self.boom = boom

        def move(self, pan=None, tilt=None, source="autonomy", priority=30):
            if self.boom:
                raise ValueError("arbiter internal crash")
            seen.append({"pan": pan, "tilt": tilt, "source": source})
            return {"ok": True, "pan": pan, "tilt": tilt}

    w = HeadArbiterTransportWrapper(RecordingArbiter())
    wrapped = w.wrap_command({"cmd": "track", "pan": 0.0, "tilt": 0.0}, source="vlm_bridge")
    assert wrapped["pan"] == 0.0 and wrapped["tilt"] == 0.0
    assert seen[-1]["pan"] == 0.0 and seen[-1]["tilt"] == 0.0

    # Exception in arbiter must FAIL CLOSED (deny command)
    w_boom = HeadArbiterTransportWrapper(RecordingArbiter(boom=True))
    res = w_boom.check_and_wrap({"cmd": "track", "pan": 90.0, "tilt": 90.0})
    assert res.allowed is False
    assert "arbiter_error" in (res.reason or "")

    # ArduinoDriver.set_head sends a single atomic track command with source
    sent_requests: list[tuple[dict, str]] = []

    class StubSvc:
        def request(self, obj, timeout=None, source="autonomy"):
            sent_requests.append((obj, source))
            return {"ok": True}

        def track(self, source="autonomy", **kwargs):
            return self.request({"cmd": "track", **{k: v for k, v in kwargs.items() if v is not None}}, source=source)

    drv = ArduinoDriver(svc=StubSvc())  # type: ignore[arg-type]
    out = drv.set_head(tilt=75.0, pan=110.0, source="vlm_bridge")
    assert out == {"ok": True}
    assert len(sent_requests) == 1
    assert sent_requests[0][0]["cmd"] == "track"
    assert sent_requests[0][0]["pan"] == 110.0 and sent_requests[0][0]["tilt"] == 75.0
    assert sent_requests[0][1] == "vlm_bridge"


def test_validators_reject_bool_nan_and_new_builders_and_catalog() -> None:
    assert validate_arduino_payload({"cmd": "set_servo", "index": True, "deg": 90}) is not None
    assert validate_arduino_payload({"cmd": "set_servo", "index": 0, "deg": False}) is not None
    assert validate_arduino_payload({"cmd": "set_servo", "index": 0, "deg": float("nan")}) is not None
    assert validate_arduino_payload({"cmd": "set_servo", "index": 0, "deg": float("inf")}) is not None
    assert validate_arduino_payload(build_ack_cmd(12)) is None
    assert validate_arduino_payload(build_telemetry_start_cmd(150)) is None

    svc = xArduinoSerialService(config_overrides={"watchdog": {"enabled": False}})
    assert "happy" in svc.CUTE_SOUND_CATALOG
    assert svc._resolve_request_timeout(1.0) == 1.0
    assert svc._resolve_request_timeout(None) == svc.cfg["request_timeout_ms"] / 1000.0
    svc.stop()


def test_router_http_codes_watchdog_endpoints_and_hello_fw_check() -> None:
    svc = xArduinoSerialService(
        config_overrides={
            "transport": "esp_http",
            "auto_heartbeat": False,
            "min_firmware_version": "2.0.0",
            "required_capabilities": ["pid", "rfid"],
            "watchdog": {"enabled": True, "timeout_s": 0.15, "check_interval_s": 0.03, "only_while_moving": True},
        }
    )
    sess = _FakeSession(
        lambda u, b, p, t: (
            _FakeResponse(200, {"ok": True})
            if u.endswith("/send")
            else _FakeResponse(
                200,
                {"ok": True, "resp": {"ok": True, "fw_ver": "1.5.0", "capabilities": ["pid"]}},
            )
        )
    )
    svc._esp_http = sess

    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    # Incompatible fw_ver marks /healthz ok=False while surfacing diagnostics
    hz = client.get("/arduino/healthz")
    assert hz.status_code == 200
    assert hz.json()["ok"] is False
    assert hz.json()["firmware"]["compatible"] is False
    assert hz.json()["firmware"]["fw_ver"] == "1.5.0"

    # Thread-safe metrics snapshot
    mt = client.get("/arduino/metrics")
    assert mt.status_code == 200 and mt.json()["tx_count"] >= 1

    # Watchdog status + only_while_moving guard + reset
    wd = svc.watchdog
    assert isinstance(wd, HardwareSafetyWatchdog)
    wd.start()
    time.sleep(0.22)
    # Stationary while only_while_moving=True -> should not trip yet
    assert client.get("/arduino/watchdog/status").json()["tripped"] is False
    wd.set_motion_state(True)
    time.sleep(0.25)
    st = client.get("/arduino/watchdog/status").json()
    assert st["tripped"] is True
    assert "moving=True" in st["trip_reason"]

    rst = client.post("/arduino/watchdog/reset")
    assert rst.status_code == 200 and rst.json()["tripped"] is False
    wd.stop()

    # Error HTTP code mapping: 400 invalid payload, 403 arbiter denied, 503 offline
    assert client.post("/arduino/send", json={"cmd": "not_real"}).status_code == 400
    svc._esp_note_failure(ConnectionError("down"))
    svc._esp_paused_until = time.monotonic() + 60.0
    assert client.post("/arduino/send", json={"cmd": "hello"}).status_code == 503

    def _arb_deny(*_a, **_k):
        raise RuntimeError("Head movement denied by arbiter: priority")

    svc.send = _arb_deny  # type: ignore[method-assign]
    assert client.post("/arduino/send", json={"cmd": "set_servo", "index": 0, "deg": 90}).status_code == 403
    svc.stop()


def test_background_telemetry_worker_closes_cleanly() -> None:
    posted: list[dict] = []

    class DummySession:
        def post(self, url, json=None, timeout=None):
            posted.append(json)

        def close(self):
            pass

    svc = xArduinoSerialService(
        config_overrides={
            "transport": "serial",
            "auto_heartbeat": False,
            "watchdog": {"enabled": False},
            "telemetry": {"enabled": True, "endpoint": "http://telemetry.local/events"},
        }
    )
    import modules.arduino_serial.services.serial_loops as sl_mod

    orig_req = sl_mod.requests
    sl_mod.requests = type("R", (), {"Session": lambda: DummySession()})
    try:
        svc._emit_telemetry_event("arduino_ack", {"seq": 5})
        deadline = time.monotonic() + 1.0
        while not posted and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(posted) == 1 and posted[0]["type"] == "arduino_ack"
    finally:
        svc.stop()
        sl_mod.requests = orig_req
