from modules.expression.services.output_bridge import ExpressionOutputBridge
from modules.expression.services.state import SemanticExpressionEngine


def test_output_bridge_plan_from_semantic_expression_state():
    engine = SemanticExpressionEngine()
    engine.event("autonomy.look_around", {})
    bridge = ExpressionOutputBridge(engine)
    plan = bridge.plan()
    assert plan["ok"] is True
    assert plan["action_count"] == 3
    components = {a["component"] for a in plan["actions"]}
    assert {"neopixel", "oled_faces", "piservo"}.issubset(components)
    led = [a for a in plan["actions"] if a["component"] == "neopixel"][0]
    assert led["payload"]["mode"] in {"eye", "listen", "listen_vu", "thinking", "off"}
    assert led["payload"]["eye_color"].startswith("#")


def test_output_bridge_apply_is_dry_run_by_default():
    engine = SemanticExpressionEngine()
    bridge = ExpressionOutputBridge(engine)
    result = bridge.apply()
    assert result["ok"] is True
    assert result["applied"] is False
    assert result["reason"] == "dry_run"
    assert result["plan"]["action_count"] == 3


def test_output_bridge_overrides_targets_without_mutating_engine_state():
    engine = SemanticExpressionEngine()
    bridge = ExpressionOutputBridge(engine)
    result = bridge.apply(overrides={"led": {"mode": "listen", "color": "#00ffcc"}})
    led = [a for a in result["plan"]["actions"] if a["component"] == "neopixel"][0]
    assert led["payload"] == {"mode": "listen", "eye_color": "#00ffcc"}
    assert engine.get_state()["targets"]["led"]["color"] != "#00ffcc"
