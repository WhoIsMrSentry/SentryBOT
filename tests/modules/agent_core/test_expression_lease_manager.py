from __future__ import annotations

from modules.agent_core.services.expression_arbiter import (
    ExpressionLeaseManager,
    ExpressionArbiter,
)


def test_expression_lease_manager_and_alias():
    # Verify backward compatible alias points to same class
    assert ExpressionArbiter is ExpressionLeaseManager

    manager = ExpressionLeaseManager()
    claimed = manager.claim_lights("test_source", priority=50.0, ttl_s=1.0)
    assert claimed
    st = manager.status()
    assert st["lights_owner"] == "test_source"

    manager.release("test_source")
    st = manager.status()
    assert st["lights_owner"] == ""
