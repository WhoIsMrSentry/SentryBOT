from modules.vlm_bridge.services.vision_request_gate import VisionRequestGate


def test_gate_allows_first_request_and_blocks_inflight():
    gate = VisionRequestGate({"max_inflight": 1, "reason_cooldowns_s": {"scene_change": 10}})
    first = gate.decide(reason="scene_change", scene_key="a", now=100.0)
    assert first.allowed is True
    gate.mark_start(first.request_id, reason="scene_change")
    second = gate.decide(reason="scene_change", scene_key="b", now=101.0)
    assert second.allowed is False
    assert second.mode == "inflight"
    gate.mark_finish(first.request_id, ok=True)
    stats = gate.get_stats()
    assert stats["stats"]["approved"] == 1
    assert stats["stats"]["denied"] == 1


def test_gate_uses_cooldown_and_cache_hint():
    gate = VisionRequestGate({"reason_cooldowns_s": {"boredom": 30}, "cache_ttl_s": 45})
    first = gate.decide(reason="boredom", scene_key="room", now=10.0)
    assert first.allowed is True
    second = gate.decide(reason="boredom", scene_key="room", has_cache=True, cache_age_s=12.0, now=20.0)
    assert second.allowed is False
    assert second.mode == "cooldown"
    assert second.use_cache is True
    assert second.wait_s > 0


def test_user_question_force_bypasses_cooldown_after_finish():
    gate = VisionRequestGate({"reason_cooldowns_s": {"user_question": 60}})
    first = gate.decide(reason="user_question", force=True, now=1.0)
    assert first.allowed is True
    gate.mark_start(first.request_id)
    gate.mark_finish(first.request_id)
    second = gate.decide(reason="user_question", force=True, now=2.0)
    assert second.allowed is True
