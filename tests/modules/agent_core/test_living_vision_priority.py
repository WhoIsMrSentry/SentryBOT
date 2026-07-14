from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.vlm_bridge.services.head_control_arbiter import HeadControlArbiter, HeadCommand


def test_owner_priority_beats_idle_movement():
    arb = ActionArbiter()
    owner = arb.submit(
        ActionRequest(type="head_move", source="owner_follow", priority=85, ttl_ms=2000, payload={"pan": 95, "tilt": 90})
    )
    idle = arb.submit(
        ActionRequest(type="head_move", source="autonomy", priority=30, ttl_ms=2000, payload={"pan": 100, "tilt": 90})
    )
    assert owner["ok"] is True
    assert idle["ok"] is False
    assert idle["reason"] == "resource_locked"


def test_hazard_beats_owner_follow():
    arb = ActionArbiter()
    owner = arb.submit(
        ActionRequest(type="head_move", source="owner_follow", priority=85, ttl_ms=3000, payload={"pan": 95, "tilt": 90})
    )
    hazard = arb.submit(
        ActionRequest(type="head_move", source="safety", priority=95, ttl_ms=3000, payload={"pan": 80, "tilt": 85})
    )
    assert owner["ok"] is True
    assert hazard["ok"] is True


def test_head_control_arbiter_priority_order_works():
    arb = HeadControlArbiter({"max_rate_hz": 200.0})
    arb.lock_source("owner_follow", duration_s=1.0)
    low = arb.request_move(HeadCommand(pan=120, tilt=100, source="autonomy", priority=30, ttl_s=1.0))
    high = arb.request_move(HeadCommand(pan=110, tilt=95, source="safety", priority=95, ttl_s=1.0))
    assert low["ok"] is False
    assert low["reason"] == "source_locked"
    assert high["ok"] is True

