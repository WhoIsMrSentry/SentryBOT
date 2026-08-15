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


def test_executor_routes_semantic_expression_to_companion_face_api():
    ex = CompanionGoalExecutor()
    result = ex.execute(
        {
            "safe_to_execute": True,
            "actions": [
                {"type": "expression", "event": "semantic.curious_scan", "semantic": "curious_scan", "revision": "goal-42"},
            ],
        },
        dry_run=True,
        now=100.0,
    )
    step = result["steps"][0]
    assert step["component"] == "neopixel"
    assert step["url"] == "/neopixel/companion/semantic"
    assert step["payload"] == {"semantic": "curious_scan", "revision": "goal-42"}

def test_executor_routes_navigation_policy_to_autonomy_goal():
    ex = CompanionGoalExecutor({"enabled": True, "dry_run_default": True})
    result = ex.execute(
        {
            "plan_id": "goal-navigation",
            "behavior": "curious_scan",
            "actions": [{"type": "navigation", "policy": "safe_exploration", "risk": "low"}],
        },
        dry_run=True,
        pc_test=True,
        now=100.0,
    )
    step = result["steps"][0]
    assert step["component"] == "autonomy"
    assert step["url"] == "/autonomy/navigation/goal"
    assert step["capability"] == "navigation.safe_exploration"
    assert step["payload"]["companion_policy"] == "safe_exploration"

def test_executor_reports_yaml_lifecycle_for_dry_run():
    executor = CompanionGoalExecutor(
        {
            "enabled": True,
            "dry_run_default": True,
            "lifecycle": {
                "enabled": True,
                "dry_run_state": "simulated",
                "applied_state": "completed",
                "unavailable_state": "blocked",
                "failure_state": "failed",
                "cancelled_reasons": [],
            },
        }
    )
    result = executor.execute(sample_plan(), dry_run=True, pc_test=True, now=100.0)
    assert result["lifecycle"]["state"] == "simulated"
    assert result["lifecycle"]["reason"] == "dry_run"

def test_executor_blocks_capability_guard_before_steps():
    executor = CompanionGoalExecutor(
        {
            "enabled": True,
            "dry_run_default": False,
            "allow_real_hardware": True,
            "require_capability_guard": True,
        }
    )
    plan = sample_plan()
    plan["capability_guard"] = {"blocked": True, "reason": "capability_unavailable"}
    result = executor.execute(plan, dry_run=False, pc_test=False, now=100.0)
    assert result["applied"] is False
    assert result["reason"] == "capability_guard_blocked"
    assert result["steps"] == []
