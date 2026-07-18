from __future__ import annotations

from modules.autonomy.services.companion_goal_executor import (
    AUTONOMY_SEMANTIC_NOOP_CONTRACT,
    AUTONOMY_SEMANTIC_NOOP_ROLE,
    CompanionGoalExecutor,
)


def test_wait_action_is_explicit_safe_semantic_noop_step():
    executor = CompanionGoalExecutor({"dry_run_default": True})
    result = executor.execute(
        {
            "plan_id": "p1",
            "safe_to_execute": True,
            "actions": [{"type": "wait", "label": "calm_idle"}],
        },
        dry_run=True,
        pc_test=True,
        now=1.0,
    )
    assert AUTONOMY_SEMANTIC_NOOP_CONTRACT is True
    assert AUTONOMY_SEMANTIC_NOOP_ROLE == "safe_semantic_passive_goal_step"
    assert result["applied"] is False
    assert result["dry_run"] is True
    assert result["steps"][0]["component"] == "scheduler"
    assert result["steps"][0]["method"] == "NOOP"
    assert result["steps"][0]["url"] == "noop:wait"
    assert result["steps"][0]["risk"] == "none"


def test_unknown_action_becomes_safe_noop_not_raw_hardware_command():
    executor = CompanionGoalExecutor({"dry_run_default": True})
    result = executor.execute(
        {
            "plan_id": "p2",
            "safe_to_execute": True,
            "actions": [{"type": "dance", "risk": "unknown"}],
        },
        dry_run=True,
        pc_test=True,
        now=2.0,
    )
    step = result["steps"][0]
    assert step["component"] == "unknown"
    assert step["method"] == "NOOP"
    assert step["url"] == "noop:unknown_action"
    assert step["payload"] == {"type": "dance", "risk": "unknown"}
