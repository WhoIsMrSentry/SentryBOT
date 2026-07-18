from modules.autonomy.services.companion_goal_executor import CompanionGoalExecutor


def sample_plan():
    return {
        "ok": True,
        "plan_id": "exploration:look_around:look_around_and_learn",
        "dominant_need": "exploration",
        "recommended_goal": "look_around_and_learn",
        "behavior": "look_around_and_learn",
        "priority": "normal",
        "safe_to_execute": True,
        "auto_execute": False,
        "actions": [
            {"type": "expression", "event": "needs.exploration"},
            {"type": "vision", "mode": "cheap", "reason": "exploration"},
            {"type": "motion", "name": "look_around", "risk": "low"},
        ],
    }


def test_executor_dry_run_builds_steps_without_applying():
    ex = CompanionGoalExecutor({"enabled": True, "dry_run_default": True})
    result = ex.execute(sample_plan(), dry_run=True, pc_test=True, now=100.0)
    assert result["ok"] is True
    assert result["applied"] is False
    assert result["dry_run"] is True
    assert result["step_count"] == 3
    assert result["steps"][0]["component"] == "expression"
    assert result["steps"][1]["component"] == "vlm_bridge"
    assert result["steps"][2]["url"] == "/piservo/gesture?name=look_around"


def test_executor_blocks_real_execution_on_pc():
    ex = CompanionGoalExecutor({"enabled": True, "dry_run_default": False, "allow_real_hardware": True})
    result = ex.execute(sample_plan(), dry_run=False, pc_test=True, now=100.0)
    assert result["applied"] is False
    assert result["dry_run"] is True
    assert result["reason"] == "pc_real_execution_blocked"


def test_executor_blocks_real_execution_without_hardware_permission():
    ex = CompanionGoalExecutor({"enabled": True, "dry_run_default": False, "allow_real_hardware": False})
    result = ex.execute(sample_plan(), dry_run=False, pc_test=False, now=100.0)
    assert result["applied"] is False
    assert result["reason"] == "real_hardware_not_allowed"


def test_executor_wait_action_is_noop():
    ex = CompanionGoalExecutor()
    result = ex.execute({"actions": [{"type": "wait", "label": "calm_idle"}]}, dry_run=True)
    assert result["steps"][0]["component"] == "scheduler"
    assert result["steps"][0]["risk"] == "none"
