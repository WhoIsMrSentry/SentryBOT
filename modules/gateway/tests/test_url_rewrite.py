from __future__ import annotations

from modules.agent_core.services.expression_arbiter import ExpressionArbiter
from modules.gateway.url import (
    gateway_base_from_agent_cfg,
    resolve_config_url,
    rewrite_loopback_urls,
)


def test_resolve_config_url_gateway_alias():
    base = "http://127.0.0.1:9090"
    assert resolve_config_url("@gateway/camera/video", base) == "http://127.0.0.1:9090/camera/video"
    assert (
        resolve_config_url("http://localhost:8080/ollama/chat", base)
        == "http://127.0.0.1:9090/ollama/chat"
    )


def test_rewrite_nested_config():
    base = "http://127.0.0.1:8080"
    cfg = {"actions": {"endpoint": "@gateway/autonomy/apply_actions"}}
    out = rewrite_loopback_urls(cfg, base)
    assert out["actions"]["endpoint"] == "http://127.0.0.1:8080/autonomy/apply_actions"


def test_gateway_base_from_agent_cfg():
    cfg = {"actions": {"gateway_base_url": "http://192.168.1.50:8080"}}
    assert gateway_base_from_agent_cfg(cfg) == "http://192.168.1.50:8080"


def test_expression_arbiter_blocks_second_owner():
    arb = ExpressionArbiter()
    assert arb.claim_lights("speak") is True
    assert arb.claim_lights("autonomy") is False
    assert arb.claim_oled("oled_faces") is True
    assert arb.claim_oled("interactions") is False
    arb.release("speak")
    assert arb.claim_lights("autonomy") is True
