from __future__ import annotations

import sys
import types

from modules.hardware.services import i2c


def test_i2c_scan_returns_empty_when_smbus2_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "smbus2", None)
    assert i2c.scan(1) == []


def test_i2c_scan_returns_detected_addresses_and_closes(monkeypatch):
    events = {"closed": False, "bus": None}

    class FakeBus:
        def __init__(self, bus: int):
            events["bus"] = bus

        def write_quick(self, addr: int) -> None:
            if addr not in {0x12, 0x42}:
                raise OSError("no device")

        def close(self) -> None:
            events["closed"] = True

    fake_smbus2 = types.SimpleNamespace(SMBus=FakeBus)
    monkeypatch.setitem(sys.modules, "smbus2", fake_smbus2)

    assert i2c.scan(3) == [0x12, 0x42]
    assert events["bus"] == 3
    assert events["closed"] is True


def test_i2c_scan_returns_empty_when_bus_open_fails(monkeypatch):
    class FailingBus:
        def __init__(self, bus: int):
            raise OSError("i2c unavailable")

    fake_smbus2 = types.SimpleNamespace(SMBus=FailingBus)
    monkeypatch.setitem(sys.modules, "smbus2", fake_smbus2)

    assert i2c.scan(1) == []


def test_i2c_scan_contract_markers_present():
    assert i2c.I2C_SCAN_CONTRACT is True
    assert i2c.I2C_SCAN_BOUNDARY_ROLE == "pi_linux_safe_i2c_probe"
    assert i2c.I2C_SCAN_UNAVAILABLE_BEHAVIOR == "return_empty_list"
