import time
import json

from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class DummyTransportNoReply:
    def __init__(self):
        self._buf = b""
        self._read_q = []

    def readline(self):
        # do a small sleep to simulate blocking read but return no data
        time.sleep(0.01)
        if self._read_q:
            return (self._read_q.pop(0) + b"\n")
        return b""

    def write(self, data: bytes) -> int:
        self._buf += data
        return len(data)

    def close(self):
        pass


def test_request_retries_trigger_multiple_writes():
    dt = DummyTransportNoReply()
    # configure one retry (so total sends = 2)
    svc = xArduinoSerialService(config_overrides={"transport": "serial", "request_max_retries": 1}, transport_factory=lambda *a, **k: dt)
    svc.start()
    try:
        try:
            svc.request({"cmd": "hello"}, timeout=0.05)
        except Exception:
            # expected to timeout after retries
            pass

        # buffer should contain two send attempts
        data = dt._buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in data.splitlines() if ln.strip()]
        assert len(lines) >= 2, f"expected >=2 writes, got {len(lines)}: {lines}"
    finally:
        svc.stop()


def test_request_timeout_reports_echo_only_hint():
    dt = DummyTransportNoReply()
    # Simulate a line-echo peer that returns the same command without ACK fields.
    dt._read_q.append(json.dumps({"cmd": "hello"}).encode("utf-8"))

    svc = xArduinoSerialService(config_overrides={"transport": "serial", "request_max_retries": 0}, transport_factory=lambda *a, **k: dt)
    svc.start()
    try:
        try:
            svc.request({"cmd": "hello"}, timeout=0.05)
            assert False, "request should timeout when only echo-like frames are received"
        except TimeoutError as exc:
            msg = str(exc)
            assert "Echo-like frame" in msg
            assert "cmd 'hello'" in msg
    finally:
        svc.stop()
