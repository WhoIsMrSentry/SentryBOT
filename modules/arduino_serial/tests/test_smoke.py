from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class FakeTransport:
    def __init__(self, responses: Optional[List[bytes]] = None, *a, **k):
        self.buffer: list[bytes] = []
        if responses is not None:
            self._responses = list(responses)
        else:
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


def test_rfid_authorization_from_event():
    rfid_uid = "AB12FF34"
    responses = [
        b'{"ok":true,"msg":"ready"}\n',
        b'{"ok":true,"event":"rfid","uid":"' + rfid_uid.encode("utf-8") + b'"}\n',
    ]
    svc = xArduinoSerialService(
        config_overrides={"rfid": {"allowed_uids": [rfid_uid], "authorize_window_s": 5}},
        transport_factory=lambda *a, **k: FakeTransport(responses=responses),
    )
    svc.start()
    time.sleep(0.05)
    result = svc.authorize_rfid()
    assert result.get("authorized") is True
    assert result.get("uid") == rfid_uid
    svc.stop()
