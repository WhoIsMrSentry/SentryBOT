from __future__ import annotations

import threading
from typing import Dict, Any, Optional

try:
    from ..xArduinoSerialService import xArduinoSerialService
except Exception:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore

# Process-wide shared service instance (R11/R33 fix): implicit
# ArduinoDriver() constructions (e.g. piservo ears) must reuse ONE service
# instead of each opening their own serial/ESP connection + heartbeat.
_shared_svc: Optional[xArduinoSerialService] = None
_shared_lock = threading.Lock()


def set_shared_service(svc: xArduinoSerialService) -> None:
    """Register an externally-created service (e.g. the gateway instance)."""
    global _shared_svc
    with _shared_lock:
        if _shared_svc is None or _shared_svc is svc:
            _shared_svc = svc


def get_shared_service() -> xArduinoSerialService:
    """Return the shared service, creating it on first use."""
    global _shared_svc
    with _shared_lock:
        if _shared_svc is None:
            _shared_svc = xArduinoSerialService()
        return _shared_svc


class ArduinoDriver:
    """High-level convenience layer over xArduinoSerialService."""

    def __init__(self, svc: Optional[xArduinoSerialService] = None):
        self.svc = svc or get_shared_service()

    def start(self) -> None:
        self.svc.start()

    def stop(self) -> None:
        self.svc.stop()

    # shortcuts
    def hello(self) -> Dict[str, Any]:
        return self.svc.hello()

    def set_head(self, tilt: float, pan: float) -> Dict[str, Any]:
        # Current firmware mapping: index 0=pan, 1=tilt.
        self.svc.set_servo(0, float(pan))
        return self.svc.set_servo(1, float(tilt))

    def estop(self) -> Dict[str, Any]:
        return self.svc.estop()

    # lasers
    def laser_on(self, which: int) -> Dict[str, Any]:
        return self.svc.laser_on(which)

    def laser_both_on(self) -> Dict[str, Any]:
        return self.svc.laser_both_on()

    def laser_off(self) -> Dict[str, Any]:
        return self.svc.laser_off()
