"""Deprecated shim — PeopleMemory has moved to modules.cognitive_memory."""
from __future__ import annotations

import warnings

warnings.warn(
    "modules.vlm_bridge.services.people_memory is deprecated; use modules.cognitive_memory.services.people_memory instead",
    DeprecationWarning,
    stacklevel=2,
)

from modules.cognitive_memory.services.people_memory import PeopleMemory

__all__ = ["PeopleMemory"]
