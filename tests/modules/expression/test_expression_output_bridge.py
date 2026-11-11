from modules.expression.semantic.services.output_bridge import ExpressionOutputBridge
from modules.expression.semantic.services.state import SemanticExpressionEngine


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


def test_failed_output_bridge_does_not_cache_target_sig():
    engine = SemanticExpressionEngine()
    engine.event("interactions.idle", {})
    bridge = ExpressionOutputBridge(engine, cfg={"enabled": True, "gateway_url": "http://127.0.0.1:9"})
    first = bridge.apply()
    second = bridge.apply()
    assert first["ok"] is False
    assert first["reason"] == "output_failed"
    assert second["reason"] == "output_failed"


def test_successful_output_bridge_skips_unchanged_targets(monkeypatch):
    engine = SemanticExpressionEngine()
    engine.event("interactions.idle", {})
    bridge = ExpressionOutputBridge(engine, cfg={"enabled": True, "gateway_url": "http://127.0.0.1:9"})
    sent = []

    def _ok_send(action):
        sent.append(action["component"])
        return {"ok": True, "component": action["component"], "status": 200, "response": {}}

    monkeypatch.setattr(bridge, "_send", _ok_send)
    first = bridge.apply()
    second = bridge.apply()
    assert first["ok"] is True
    assert first["reason"] == "applied"
    assert len(sent) == 3
    assert second["ok"] is True
    assert second["reason"] == "unchanged"
    assert len(sent) == 3
