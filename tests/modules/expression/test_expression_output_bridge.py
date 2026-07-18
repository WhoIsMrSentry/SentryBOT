from modules.expression.services.output_bridge import ExpressionOutputBridge
from modules.expression.services.state import SemanticExpressionEngine


def test_output_bridge_plan_from_semantic_expression_state():
    engine = SemanticExpressionEngine()
    engine.event("autonomy.look_around", {})
    bridge = ExpressionOutputBridge(engine)
    plan = bridge.plan()
    assert plan["ok"] is True
    assert len(plan["actions"]) == 3
    components = {a["component"] for a in plan["actions"]}
    assert {"neopixel", "oled_faces", "piservo"}.issubset(components)
    led = [a for a in plan["actions"] if a["component"] == "neopixel"][0]
    assert led["payload"]["mode"] in {"eye", "listen", "listen_vu", "thinking", "off"}
    assert led["payload"]["eye_color"].startswith("#")


def test_output_bridge_apply_is_disabled_when_cfg_says_so():
    engine = SemanticExpressionEngine()
    bridge = ExpressionOutputBridge(engine, cfg={"enabled": False})
    result = bridge.apply()
    assert result["ok"] is False
    assert result["applied"] is False
    assert result["reason"] == "bridge_disabled"
