"""Admin UI service shim.

The Admin UI is gateway-bound; this class exists mainly so callers can ask the
aggregator for snapshots without having to know about the router internals.
"""

from __future__ import annotations

from typing import Any, Dict

from .config_loader import load_config
from .services.dashboard import DashboardAggregator


class xAdminUiService:
    def __init__(self, started: Dict[str, Any], config: Dict[str, Any] | None = None) -> None:
        self.config = load_config(None) if config is None else dict(config)
        self.started = started
        self.aggregator = DashboardAggregator(started)

    @property
    def mount_prefix(self) -> str:
        return str(self.config.get("mount_prefix", "/admin") or "/admin")

    def snapshot(self) -> Dict[str, Any]:
        return self.aggregator.all_snapshots()
