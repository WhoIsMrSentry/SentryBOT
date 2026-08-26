"""Compatibility boundary: LED/OLED visual lease manager.

Canonical implementation lives in ``modules.common.led_write_policy``; this
module only re-exports it under the historical names so existing imports,
routes and tests keep working.
"""
from __future__ import annotations

from modules.common.led_write_policy import (  # noqa: F401
    CANONICAL_PRIORITIES,
    FORCE_SOURCES,
    LedWritePolicy,
    get_shared_policy,
    reset_shared_policy,
    to_canonical_priority,
)

EXPRESSION_IDLE_COMPATIBILITY = True
EXPRESSION_IDLE_BOUNDARY_ROLE = "agent_core_compat_expression_arbiter"
EXPRESSION_IDLE_RUNTIME_OWNER = "central state/output: modules.expression compatibility boundary"

ExpressionLeaseManager = LedWritePolicy
ExpressionArbiter = LedWritePolicy

__all__ = [
    "CANONICAL_PRIORITIES",
    "FORCE_SOURCES",
    "LedWritePolicy",
    "ExpressionLeaseManager",
    "ExpressionArbiter",
    "get_shared_policy",
    "reset_shared_policy",
    "to_canonical_priority",
]
