"""Unified social SQLite store shared by VLM bridge, autonomy and interactions.

Exposes a single :class:`SocialDB` aggregator that bundles repositories for
persons, face descriptors, sightings, chat episodes, relationships, moments,
mood snapshots, rituals, interaction events and owner sessions.

Modules typically obtain a shared instance through :func:`get_default` and
delegate persistence calls to the repositories. JSON-backed adapters keep
working when no instance is registered, which preserves backward compatibility
in degraded environments.
"""

from .db import SocialDB, get_default, set_default, reset_default

__all__ = ["SocialDB", "get_default", "set_default", "reset_default"]
