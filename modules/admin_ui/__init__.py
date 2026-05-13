"""SentryBOT admin UI module.

Single LAN-only management surface served from ``/admin/*``. Exposes a vanilla
HTML + JS dashboard backed by aggregator endpoints and a Server-Sent Events
stream that fan-outs arbiter / vision / social status snapshots.
"""

from .services.dashboard import DashboardAggregator
from .xAdminUiService import xAdminUiService

__all__ = ["DashboardAggregator", "xAdminUiService"]
