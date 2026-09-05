from __future__ import annotations

import os
from typing import Any, Callable, Optional

_PI_SERIAL_CANDIDATE_GLOBS: tuple[str, ...] = (
    "/dev/serial/by-id/*",
    "/dev/serial/by-path/*",
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
)


def _existing_device_from_globs(patterns: tuple[str, ...] = _PI_SERIAL_CANDIDATE_GLOBS) -> str | None:
    from glob import glob

    for pattern in patterns:
        matches = sorted(glob(pattern))
        if matches:
            return matches[0]
    return None


def _default_serial_device() -> str:
    env_device = (os.getenv("SENTRYBOT_SERIAL_DEVICE") or os.getenv("SENTRYBOT_ARDUINO_DEVICE") or "").strip()
    if env_device:
        return env_device
    if os.name == "nt":
        return "COM3"
    import sys
    this_mod = sys.modules.get("modules.arduino_serial.xArduinoSerialService") or sys.modules.get(__name__)
    glob_fn = getattr(this_mod, "_existing_device_from_globs", _existing_device_from_globs)
    return glob_fn() or "/dev/serial0"


def _autodetect_port(fallback: Optional[str]) -> str:
    import sys
    this_mod = sys.modules.get("modules.arduino_serial.xArduinoSerialService") or sys.modules.get(__name__)
    active_serial = getattr(this_mod, "serial", globals().get("serial"))
    if active_serial is None:
        if fallback:
            return fallback
        raise RuntimeError("pyserial not installed")
    ports = list(active_serial.tools.list_ports.comports())

    def _text(v: Any) -> str:
        return str(v or "").lower()

    def _is_arduino_like(p: Any) -> bool:
        txt = " ".join(
            [
                _text(getattr(p, "description", "")),
                _text(getattr(p, "manufacturer", "")),
                _text(getattr(p, "product", "")),
                _text(getattr(p, "hwid", "")),
            ]
        )
        keys = ("arduino", "mega", "2560", "ch340", "cp210", "usb serial")
        return any(k in txt for k in keys)

    # 1) Prefer Arduino-like USB serial adapters first.
    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")) and _is_arduino_like(p):
            return dev

    # 2) Then any USB serial-style device.
    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")):
            return dev

    # 3) Prefer known UART names if no USB serial device is found.
    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if any(x in dev for x in ("/dev/ttyAMA0", "/dev/serial0", "/dev/ttyS0")):
            return dev

    # 4) Any port that identifies as Arduino-like.
    for p in ports:
        if _is_arduino_like(p):
            dev = str(getattr(p, "device", "") or "")
            if dev:
                return dev

    # 5) If Raspberry Pi UART path exists, use it as last Linux fallback.
    path_exists = getattr(getattr(this_mod, "os", os), "path", os.path).exists
    try:
        if path_exists("/dev/serial0"):
            return "/dev/serial0"
    except Exception:
        pass

    if ports:
        first = str(getattr(ports[0], "device", "") or "")
        if first:
            return first
    if fallback:
        return fallback
    default_dev_fn = getattr(this_mod, "_default_serial_device", _default_serial_device)
    return default_dev_fn()
