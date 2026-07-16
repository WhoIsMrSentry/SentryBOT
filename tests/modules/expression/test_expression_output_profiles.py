from modules.expression.services.output_bridge import ExpressionOutputBridge
from modules.expression.services.state import SemanticExpressionEngine


def test_output_bridge_defaults_to_pc_dry_run_profile():
    bridge = ExpressionOutputBridge(SemanticExpressionEngine(), cfg={})
    profile = bridge.profile()
    assert profile["active_profile"] == "pc_dry_run"
    assert profile["dry_run_default"] is True
    assert profile["enabled"] is False
    assert profile["allow_real_hardware"] is False


def test_output_bridge_robot_profile_can_plan_real_actions():
    engine = SemanticExpressionEngine()
    engine.event("autonomy.look_around", {})
    bridge = ExpressionOutputBridge(engine, cfg={"active_profile": "robot_safe"})
    plan = bridge.plan()
    assert plan["active_profile"] == "robot_safe"
    assert plan["dry_run_default"] is False
    assert plan["enabled"] is True
    assert plan["allow_real_hardware"] is True
    assert plan["action_count"] == 3


def test_pc_profile_blocks_real_hardware_apply():
    bridge = ExpressionOutputBridge(SemanticExpressionEngine(), cfg={"active_profile": "pc_dry_run"})
    result = bridge.apply(dry_run=False)
    assert result["ok"] is False
    assert result["reason"] == "profile_blocks_real_hardware"
    assert result["applied"] is False


def test_set_profile_accepts_known_profile_only():
    bridge = ExpressionOutputBridge(SemanticExpressionEngine(), cfg={})
    assert bridge.set_profile("robot_safe")["ok"] is True
    bad = bridge.set_profile("unknown")
    assert bad["ok"] is False
    assert bad["error"] == "unknown_profile"
