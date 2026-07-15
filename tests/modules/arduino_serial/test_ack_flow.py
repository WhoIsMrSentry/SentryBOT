import threading
import time
import json

from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class DummyTransport:
    def __init__(self):
        self._buf = b""
        self._read_q = []

    def readline(self):
        # simulate blocking read with small wait
        time.sleep(0.01)
        if self._read_q:
            return (self._read_q.pop(0) + b"\n")
        return b""

    def write(self, data: bytes) -> int:
        # capture writes for test
        self._buf += data
        return len(data)

    def close(self):
        pass


def test_ack_sent_for_neopixel_request():
    dt = DummyTransport()
    svc = xArduinoSerialService(config_overrides={"transport": "serial"}, transport_factory=lambda *a, **k: dt)
    svc.start()
    # inject a neopixel_request as if from Arduino
    dt._read_q.append(json.dumps({"event": "neopixel_request", "name": "PULSE", "seq": 42}).encode("utf-8"))
    time.sleep(0.1)
    # Writer thread should have enqueued an ACK JSON line; ignore whitespace formatting.
    lines = [ln for ln in dt._buf.decode("utf-8", errors="ignore").splitlines() if ln.strip()]
    parsed = []
    for ln in lines:
        try:
            parsed.append(json.loads(ln))
        except Exception:
            continue
    assert any(obj.get("ack_seq") == 42 for obj in parsed)
    svc.stop()
