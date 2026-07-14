from __future__ import annotations

import importlib
from types import SimpleNamespace

service_mod = importlib.import_module("modules.arduino_serial.xArduinoSerialService")


def _fake_port(
    device: str,
    description: str = "",
    manufacturer: str = "",
    product: str = "",
    hwid: str = "",
):
    return SimpleNamespace(
        device=device,
        description=description,
        manufacturer=manufacturer,
        product=product,
        hwid=hwid,
    )


def _set_fake_serial(monkeypatch, ports):
    fake_serial = SimpleNamespace(
        tools=SimpleNamespace(
            list_ports=SimpleNamespace(comports=lambda: ports)
        )
    )
    monkeypatch.setattr(service_mod, "serial", fake_serial)


def test_autodetect_prefers_usb_arduino_over_serial0(monkeypatch):
    ports = [
        _fake_port(device="/dev/ttyAMA0", description="UART"),
        _fake_port(device="/dev/ttyACM0", description="Arduino Mega 2560", manufacturer="Arduino"),
    ]
    _set_fake_serial(monkeypatch, ports)
    monkeypatch.setattr(service_mod.os.path, "exists", lambda p: p == "/dev/serial0")

    port = service_mod.xArduinoSerialService._autodetect_port(None)
    assert port == "/dev/ttyACM0"


def test_autodetect_falls_back_to_serial0_when_no_ports(monkeypatch):
    _set_fake_serial(monkeypatch, [])
    monkeypatch.setattr(service_mod.os.path, "exists", lambda p: p == "/dev/serial0")

    port = service_mod.xArduinoSerialService._autodetect_port(None)
    assert port == "/dev/serial0"
