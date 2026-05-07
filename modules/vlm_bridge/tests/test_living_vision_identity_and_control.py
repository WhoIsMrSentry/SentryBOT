import tempfile
import time


def test_low_confidence_person_not_owner():
    from modules.vlm_bridge.services.person_identity import PersonIdentityManager

    with tempfile.TemporaryDirectory() as td:
        store = f"{td}/people.json"
        mgr = PersonIdentityManager(store_path=store)
        rec = mgr.remember_person("TestUser", relationship="known", recognition_level=1)
        assert rec.recognition_level == 1
        assert mgr.is_owner("TestUser") is False


def test_person_memory_persists_across_restart():
    from modules.vlm_bridge.services.person_identity import PersonIdentityManager

    with tempfile.TemporaryDirectory() as td:
        store = f"{td}/people.json"
        mgr1 = PersonIdentityManager(store_path=store)
        mgr1.remember_person("Emir", relationship="owner", recognition_level=5)
        mgr1.save()

        mgr2 = PersonIdentityManager(store_path=store)
        rec = mgr2.get_person("Emir")
        assert rec is not None
        assert rec.recognition_level == 5
        assert rec.relationship == "owner"


def test_remember_person_updates_recognition_level():
    from modules.vlm_bridge.services.person_identity import PersonIdentityManager

    with tempfile.TemporaryDirectory() as td:
        store = f"{td}/people.json"
        mgr = PersonIdentityManager(store_path=store)
        mgr.remember_person("Alice", relationship="known", recognition_level=2)
        rec = mgr.remember_person("Alice", relationship="friend", recognition_level=3)
        assert rec.recognition_level == 3
        assert rec.relationship == "friend"


def test_duplicate_pan_tilt_commands_suppressed():
    from modules.vlm_bridge.services.head_control_arbiter import HeadControlArbiter

    arb = HeadControlArbiter({"deadband_deg": 3, "max_rate_hz": 1000})
    first = arb.move(100, 95, source="manual", priority=100)
    time.sleep(0.01)
    second = arb.move(96, 93, source="manual", priority=100)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "deadband"


def test_follow_mode_does_not_spam_vlm_calls():
    from modules.vlm_bridge.services.vision_sampler import VisionSampler

    sampler = VisionSampler({"min_interval_s": 5, "suppress_during_follow": True})
    should = sampler.should_call_vlm(
        new_person=True,
        follow_mode_active=True,
        user_question=False,
        hazard_detected=False,
    )
    assert should is False
