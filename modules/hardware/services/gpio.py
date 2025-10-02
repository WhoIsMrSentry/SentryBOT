from __future__ import annotations
from typing import Any


class GPIO:
    def __init__(self, mode: str = "bcm") -> None:
        self.mode = mode

    def info(self) -> dict[str, Any]:
        return {"mode": self.mode, "available": False}
