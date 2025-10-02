from __future__ import annotations

import json
from typing import Any, Dict

from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class FakeTransport:
    def __init__(self, *a, **k):
        self.buffer: list[bytes] = []
        self._responses = [
            b'{"ok":true,"msg":"ready"}\n',
            b'{"ok":true}\n',
        ]

    def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""

    def write(self, data: bytes) -> int:
        self.buffer.append(data)
        return len(data)

    def close(self) -> None:
        pass


def test_smoke_hello_and_send():
    svc = xArduinoSerialService(transport_factory=lambda *a, **k: FakeTransport())
    svc.start()
    # hello request should get a response
    resp: Dict[str, Any] = svc.hello()
    assert resp.get("ok") is True
    # send a command (no response check)
    svc.send({"cmd": "hb"})
    assert any(b'"hb"' in x for x in svc._ser.buffer)  # type: ignore[attr-defined]
    svc.stop()
