from __future__ import annotations

import os
from typing import Any, Callable, Optional

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except Exception:  # pragma: no cover
    serial = None

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


def _default_serial_device(
    *,
    glob_fn: Optional[Callable[[], str | None]] = None,
) -> str:
    env_device = (os.getenv("SENTRYBOT_SERIAL_DEVICE") or os.getenv("SENTRYBOT_ARDUINO_DEVICE") or "").strip()
    if env_device:
        return env_device
    if os.name == "nt":
        return "COM3"
    resolver = glob_fn or _existing_device_from_globs
    return resolver() or "/dev/serial0"


def _autodetect_port(
    fallback: Optional[str],
    *,
    serial_module: Any = None,
    exists_fn: Optional[Callable[[str], bool]] = None,
    default_device_fn: Optional[Callable[[], str]] = None,
) -> str:
    active_serial = serial if serial_module is None else serial_module
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

    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")) and _is_arduino_like(p):
            return dev

    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if dev and any(x in dev for x in ("ttyACM", "ttyUSB", "COM")):
            return dev

    for p in ports:
        dev = str(getattr(p, "device", "") or "")
        if any(x in dev for x in ("/dev/ttyAMA0", "/dev/serial0", "/dev/ttyS0")):
            return dev

    for p in ports:
        if _is_arduino_like(p):
            dev = str(getattr(p, "device", "") or "")
            if dev:
                return dev

    path_exists = exists_fn or os.path.exists
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
    default_fn = default_device_fn or _default_serial_device
    return default_fn()
