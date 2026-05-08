"""Expression arbitration for lights/OLED conflicts."""

from __future__ import annotations

import threading
from typing import Dict, Any


class ExpressionArbiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lights_owner = ""
        self._oled_owner = ""

    def claim_lights(self, source: str, force: bool = False) -> bool:
        with self._lock:
            if self._lights_owner and self._lights_owner != source and not force:
                return False
            self._lights_owner = source
            return True

    def claim_oled(self, source: str, force: bool = False) -> bool:
        with self._lock:
            if self._oled_owner and self._oled_owner != source and not force:
                return False
            self._oled_owner = source
            return True

    def release(self, source: str) -> None:
        with self._lock:
            if self._lights_owner == source:
                self._lights_owner = ""
            if self._oled_owner == source:
                self._oled_owner = ""

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {"lights_owner": self._lights_owner, "oled_owner": self._oled_owner}

