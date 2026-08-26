from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from modules.agent_core.services import agent_handlers
from modules.autonomy.services.client_parts.client_lights import ClientLightsMixin
from modules.common.led_write_policy import (
    CANONICAL_PRIORITIES,
    FORCE_SOURCES,
    LedWritePolicy,
    get_shared_policy,
    reset_shared_policy,
    to_canonical_priority,
)


def _fresh_policy(**overrides) -> LedWritePolicy:
    cfg = {
        "priorities": dict(CANONICAL_PRIORITIES),
        "force_sources": list(FORCE_SOURCES),
        "channels": {"lights": {"default_lease_s": 2.5}, "oled": {"default_lease_s": 2.5}},
    }
    cfg.update(overrides)
    return LedWritePolicy(cfg)


def test_canonical_scale_matches_plan():
    assert CANONICAL_PRIORITIES["autonomy"] == 20
    assert CANONICAL_PRIORITIES["interactions"] == 40
    assert CANONICAL_PRIORITIES["animate"] == 50
    assert CANONICAL_PRIORITIES["vlm"] == 60
    assert CANONICAL_PRIORITIES["owner_command"] == 80
    assert CANONICAL_PRIORITIES["safety_navigation"] == 90
    assert CANONICAL_PRIORITIES["hardware_protection"] == 90
    assert CANONICAL_PRIORITIES["emergency"] == 100


def test_to_canonical_priority_snaps_internal_scale():
    assert to_canonical_priority(78) == 80
    assert to_canonical_priority(74) == 70 or to_canonical_priority(74) in (70, 80)
    assert to_canonical_priority(88) == 90
    assert to_canonical_priority(45) == 40
    assert to_canonical_priority("bad") == CANONICAL_PRIORITIES["default"]


def test_concurrent_claims_highest_priority_wins():
    policy = _fresh_policy()
    results: dict[str, bool] = {}
    barrier = threading.Barrier(3)

    def claim(source: str):
        barrier.wait()
        results[source] = policy.claim_lights(source)

    threads = [
        threading.Thread(target=claim, args=("autonomy",)),
        threading.Thread(target=claim, args=("interactions",)),
        threading.Thread(target=claim, args=("emergency",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winner = [s for s, ok in results.items() if ok]
    assert policy.status()["lights_owner"] == "emergency"
    assert "emergency" in winner


def test_ttl_expiry_frees_lease_without_release():
    policy = _fresh_policy(channels={"lights": {"default_lease_s": 0.05}})
    assert policy.claim_lights("autonomy")
    assert policy.status()["lights_owner"] == "autonomy"
    time.sleep(0.08)
    assert policy.status()["lights_owner"] == ""
    assert policy.claim_lights("interactions")


def test_force_sources_preempt_but_others_cannot():
    policy = _fresh_policy()
    assert policy.claim_lights("interactions")
    assert not policy.claim_lights("owner_command", force=True)
    assert policy.claim_lights("emergency", force=True)
    assert policy.status()["lights_owner"] == "emergency"


def test_reentrant_same_source_claim_refreshes():
    policy = _fresh_policy()
    assert policy.claim_lights("autonomy", ttl_s=1.0)
    assert policy.claim_lights("autonomy", ttl_s=5.0, priority=25)
    lease = policy.detailed_status()["leases"]["lights"]
    assert lease["priority"] == 25.0
    assert lease["remaining_s"] > 4.0


class _DummyLightClient(ClientLightsMixin):
    def __init__(self, arbiter=None):
        self.urls = {}
        self.request_timeouts = {}
        self._expression_arbiter = arbiter
        self.posts: list[tuple] = []

    def _post(self, service: str, path: str, payload=None, **kwargs):
        self.posts.append((service, path, payload))
        return {"ok": True}


def test_client_lights_gate_blocks_when_higher_lease_held():
    policy = _fresh_policy()
    client = _DummyLightClient(arbiter=policy)
    assert policy.claim_lights("emergency", ttl_s=5.0)
    result = client.set_neopixel("PULSE")
    assert result == {"ok": False, "reason": "lights_locked"}
    assert client.posts == []
    lease = policy._leases["lights"]
    policy.release("emergency")
    result = client.set_neopixel("COMET", duration=1.5)
    assert result == {"ok": True}
    assert client.posts[-1][1] == "/effect"
    assert policy.status()["lights_owner"] == "autonomy"


def test_client_lights_gate_ttl_covers_effect_duration():
    policy = _fresh_policy()
    client = _DummyLightClient(arbiter=policy)
    client.set_interaction_effect("BREATHE", duration_ms=1500)
    remaining = policy.detailed_status()["leases"]["lights"]["remaining_s"]
    assert remaining is not None and 1.5 <= remaining <= 2.0


def test_lights_handler_keeps_lease_for_effect_duration():
    reset_shared_policy()
    try:
        arbiter = get_shared_policy()
        captured: dict = {}

        class _CaptureClient(_DummyLightClient):
            def set_neopixel(self, effect, emotions=None, color=None, duration=None, lease_source="autonomy"):
                captured["effect"] = effect
                captured["lease_source"] = lease_source
                return super().set_neopixel(effect, emotions=emotions, color=color, duration=duration, lease_source=lease_source)

        registered: dict[str, object] = {}

        class _StubArbiter:
            def register_handler(self, action_type, handler_fn):
                registered[action_type] = handler_fn

        stub_orchestrator = SimpleNamespace(
            autonomy_client=_CaptureClient(arbiter=arbiter),
            expression_arbiter=arbiter,
            action_arbiter=_StubArbiter(),
            speech_arbiter=None,
            safety_filter=None,
            progress_manager=None,
        )
        agent_handlers.register_default_action_handlers(stub_orchestrator)
        lights_handler = registered["lights"]

        req = SimpleNamespace(payload={"effect": "WAVE", "duration_ms": 400}, source="vlm", priority=60)
        result = lights_handler(req)
        assert result.get("ok") is True
        assert captured["lease_source"] == "vlm"
        assert arbiter.status()["lights_owner"] == "vlm"
        remaining = arbiter.detailed_status()["leases"]["lights"]["remaining_s"]
        assert remaining is not None and 0.5 <= remaining <= 1.2

        blocked = lights_handler(SimpleNamespace(payload={"effect": "X"}, source="autonomy", priority=20))
        assert blocked == {"ok": False, "reason": "lights_locked"}

        arbiter._leases["lights"]["expires_at"] = time.monotonic() - 0.01
        assert arbiter.status()["lights_owner"] == ""
    finally:
        reset_shared_policy()


def test_shared_policy_singleton_identity_and_reset():
    reset_shared_policy()
    first = get_shared_policy()
    second = get_shared_policy({"priorities": {"default": 99}})
    assert first is second
    assert second.detailed_status() is not None
    reset_shared_policy()
    third = get_shared_policy()
    assert third is not first
    reset_shared_policy()
