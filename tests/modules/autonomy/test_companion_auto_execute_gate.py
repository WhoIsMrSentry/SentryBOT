from modules.autonomy.services.companion_auto_execute_gate import CompanionAutoExecuteGate


def plan(auto=True, risk="low", priority="normal"):
    return {
        "plan_id": "boredom:choose_idle_activity:stretch_or_scan",
        "dominant_need": "boredom",
        "recommended_goal": "choose_idle_activity",
        "behavior": "choose_idle_activity",
        "priority": priority,
        "safe_to_execute": True,
        "auto_execute": auto,
        "actions": [
            {"type": "expression", "event": "needs.boredom", "risk": "none"},
            {"type": "motion", "name": "stretch_or_scan", "risk": risk},
        ],
    }


def test_gate_requires_auto_execute_flag_by_default():
    gate = CompanionAutoExecuteGate()
    out = gate.decide(plan(auto=False), dry_run=True, now=100.0)
    assert out["should_execute"] is False
    assert out["reason"] == "auto_execute_false"


def test_gate_force_allows_manual_dry_run():
    gate = CompanionAutoExecuteGate()
    out = gate.decide(plan(auto=False), dry_run=True, force=True, now=100.0)
    assert out["should_execute"] is True
    assert out["dry_run"] is True
    assert out["reason"] == "force_dry_run"


def test_gate_blocks_high_risk_action():
    gate = CompanionAutoExecuteGate()
    out = gate.decide(plan(auto=True, risk="medium"), dry_run=True, now=100.0)
    assert out["should_execute"] is False
    assert out["reason"] == "risk_blocked:medium"


def test_gate_forces_dry_run_on_pc_when_real_execution_requested():
    gate = CompanionAutoExecuteGate({"dry_run_default": False, "allow_real_hardware": True})
    out = gate.decide(plan(auto=True), dry_run=False, pc_test=True, now=100.0)
    assert out["should_execute"] is True
    assert out["dry_run"] is True
    assert out["pc_real_execution_blocked"] is True


def test_gate_applies_cooldown_for_same_plan():
    gate = CompanionAutoExecuteGate({"min_interval_s": 30})
    first = gate.decide(plan(auto=True), dry_run=True, now=100.0)
    second = gate.decide(plan(auto=True), dry_run=True, now=110.0)
    assert first["should_execute"] is True
    assert second["should_execute"] is False
    assert second["reason"] == "cooldown"
