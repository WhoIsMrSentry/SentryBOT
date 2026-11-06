"""Backward-compatibility shim for runtime_profile helpers.

Delegates directly to modules.common.config_loader as the single source of truth.
"""
from __future__ import annotations

from modules.common.config_loader import (
    _PROFILE_SECTION_KEYS,
    _deep_merge_profile,
    active_runtime_profile,
    apply_runtime_profile,
    list_runtime_profiles,
)

__all__ = [
    "_PROFILE_SECTION_KEYS",
    "_deep_merge_profile",
    "apply_runtime_profile",
    "list_runtime_profiles",
    "active_runtime_profile",
]
