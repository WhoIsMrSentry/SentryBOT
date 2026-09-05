"""Service layer for the Config Center.

Contains the :class:`RuntimeConfigRegistry` shared across the gateway. Modules
register hot-applyable keys at startup; consumers (admin UI, agent_core,
autonomy) call :meth:`RuntimeConfigRegistry.set` to update a value at runtime
and trigger registered apply callbacks. All changes are appended to the
``interaction_events`` table (kind ``config.audit``) when ``social_db`` is
available.
"""

from .runtime_registry import (
    RuntimeConfigRegistry,
    RuntimeKey,
    get_default_registry,
    set_default_registry,
)

__all__ = [
    "RuntimeConfigRegistry",
    "RuntimeKey",
    "get_default_registry",
    "set_default_registry",
]
