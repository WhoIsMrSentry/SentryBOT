from modules.autonomy.services.companion_behavior_loop import CompanionBehaviorLoop


def goal(plan_id="p1", priority="normal"):
    return {
        "plan_id": plan_id,
        "dominant_need": "exploration",
        "recommended_goal": "look_around_and_learn",
        "behavior": "look_around_and_learn",
        "priority": priority,
        "actions": [{"type": "expression", "event": "needs.exploration"}],
    }


def needs(idle=30):
    return {"idle_s": idle, "dominant_need": "exploration", "recommended_goal": "look_around_and_learn"}


def test_behavior_loop_allows_pc_dry_run_tick_after_idle():
    loop = CompanionBehaviorLoop({"interval_s": 10, "min_idle_s": 5, "dry_run": True, "force_dry_run": True})
    out = loop.decide(needs=needs(12), goal=goal(), now=100.0)
    assert out["should_tick"] is True
    assert out["dry_run"] is True
    assert out["gate_force"] is True
    assert out["reason"] == "force_dry_run"


def test_behavior_loop_blocks_fresh_idle_without_force():
    loop = CompanionBehaviorLoop({"interval_s": 10, "min_idle_s": 20})
    out = loop.decide(needs=needs(3), goal=goal(), now=100.0)
    assert out["should_tick"] is False
    assert out["reason"] == "idle_too_fresh"


def test_behavior_loop_cooldown():
    loop = CompanionBehaviorLoop({"interval_s": 30, "min_idle_s": 0})
    first = loop.decide(needs=needs(50), goal=goal(), now=100.0)
    second = loop.decide(needs=needs(55), goal=goal(), now=110.0)
    assert first["should_tick"] is True
    assert second["should_tick"] is False
    assert second["reason"] == "cooldown"


def test_behavior_loop_mark_execution():
    loop = CompanionBehaviorLoop({"interval_s": 10, "min_idle_s": 0})
    decision = loop.decide(needs=needs(50), goal=goal(), now=100.0)
    result = loop.mark_execution(decision, {"available": True, "applied": False, "reason": "dry_run"})
    assert result["executed"] is True
    assert result["applied"] is False
    assert result["execution_reason"] == "dry_run"
