from __future__ import annotations

import importlib


serial_module = importlib.import_module("modules.arduino_serial.xArduinoSerialService")


def test_default_serial_device_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("SENTRYBOT_SERIAL_DEVICE", "/dev/serial/by-id/usb-arduino-test")
    assert serial_module._default_serial_device() == "/dev/serial/by-id/usb-arduino-test"


def test_default_serial_device_prefers_arduino_env(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_SERIAL_DEVICE", raising=False)
    monkeypatch.setenv("SENTRYBOT_ARDUINO_DEVICE", "/dev/ttyACM9")
    assert serial_module._default_serial_device() == "/dev/ttyACM9"


def test_default_serial_device_pi_linux_fallback_order(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_SERIAL_DEVICE", raising=False)
    monkeypatch.delenv("SENTRYBOT_ARDUINO_DEVICE", raising=False)
    monkeypatch.setattr(serial_module.os, "name", "posix", raising=False)
    monkeypatch.setattr(serial_module, "_existing_device_from_globs", lambda patterns=serial_module._PI_SERIAL_CANDIDATE_GLOBS: "/dev/ttyACM0")
    assert serial_module._default_serial_device() == "/dev/ttyACM0"


def test_default_serial_device_pi_linux_last_resort(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_SERIAL_DEVICE", raising=False)
    monkeypatch.delenv("SENTRYBOT_ARDUINO_DEVICE", raising=False)
    monkeypatch.setattr(serial_module.os, "name", "posix", raising=False)
    monkeypatch.setattr(serial_module, "_existing_device_from_globs", lambda patterns=serial_module._PI_SERIAL_CANDIDATE_GLOBS: None)
    assert serial_module._default_serial_device() == "/dev/serial0"


def test_default_serial_device_keeps_pc_dev_fallback(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_SERIAL_DEVICE", raising=False)
    monkeypatch.delenv("SENTRYBOT_ARDUINO_DEVICE", raising=False)
    monkeypatch.setattr(serial_module.os, "name", "nt", raising=False)
    assert serial_module._default_serial_device() == "COM3"
