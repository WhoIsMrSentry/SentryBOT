from __future__ import annotations

from .config_loader import load_config
from .event_bus import get_event_bus, publish_event


class RuntimeConsoleService:
    def __init__(self, config: dict | None = None) -> None:
        self.config = load_config(config or {})
        self.bus = get_event_bus()

    def start(self) -> None:
        publish_event("CORE", "Runtime console service ready", status="READY")

    def health(self) -> dict:
        return {
            "ok": True,
            "mode": self.config.get("mode", "dashboard"),
            "events": len(list(self.bus.iter())),
        }
