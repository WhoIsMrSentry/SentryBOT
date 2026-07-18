from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass
class TerminalState:
    mode: str = "dashboard"
    status: str = "starting"
    active_trace_id: str | None = None
    last_update: float = field(default_factory=time)
    components: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def set_component(self, name: str, status: str) -> None:
        self.components[name] = status.upper()
        self.last_update = time()

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "active_trace_id": self.active_trace_id,
            "last_update": self.last_update,
            "components": dict(self.components),
            "details": dict(self.details),
        }
