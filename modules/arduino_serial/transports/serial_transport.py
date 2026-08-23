from __future__ import annotations

from typing import Optional

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover
    serial = None  # pyserial optional until installed

# Single source of truth for port detection lives in services/port_detector.py
# (it additionally covers /dev/serial/by-path/*). Re-exported here so the
# historical `transports` import surface keeps working (R13 consolidation).
from ..services.port_detector import (  # noqa: F401
    _PI_SERIAL_CANDIDATE_GLOBS,
    _autodetect_port,
    _default_serial_device,
    _existing_device_from_globs,
)


class SerialTransport:
    """Thin wrapper around pyserial for dependency injection in tests."""

    def __init__(self, port: str, baudrate: int, timeout: float, write_timeout: float):
        if serial is None:
            raise RuntimeError("pyserial not installed")
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=write_timeout,
        )

    def readline(self) -> bytes:
        return self._ser.readline()

    def write(self, data: bytes) -> int:
        return self._ser.write(data)

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass


__all__ = [
    "SerialTransport",
    "_PI_SERIAL_CANDIDATE_GLOBS",
    "_autodetect_port",
    "_default_serial_device",
    "_existing_device_from_globs",
]
