from __future__ import annotations

from typing import Dict, Any, Optional

try:
    from ..xArduinoSerialService import xArduinoSerialService
except Exception:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore


class ArduinoDriver:
    """High-level convenience layer over xArduinoSerialService."""

    def __init__(self, svc: Optional[xArduinoSerialService] = None):
        self.svc = svc or xArduinoSerialService()

    def start(self) -> None:
        self.svc.start()

    def stop(self) -> None:
        self.svc.stop()

    # shortcuts
    def hello(self) -> Dict[str, Any]:
        return self.svc.hello()

    def set_head(self, tilt: float, pan: float) -> Dict[str, Any]:
        # 6 tilt, 7 pan indexes per firmware README
        self.svc.set_servo(6, float(tilt))
        return self.svc.set_servo(7, float(pan))

    def estop(self) -> Dict[str, Any]:
        return self.svc.estop()

    # lasers
    def laser_on(self, which: int) -> Dict[str, Any]:
        return self.svc.laser_on(which)

    def laser_both_on(self) -> Dict[str, Any]:
        return self.svc.laser_both_on()

    def laser_off(self) -> Dict[str, Any]:
        return self.svc.laser_off()
