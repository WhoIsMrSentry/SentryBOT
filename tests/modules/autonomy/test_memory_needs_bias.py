from modules.autonomy.services.memory_needs_bias import MemoryNeedsBias


def base_needs(**scores):
    merged = {
        "social": 40.0,
        "curiosity": 40.0,
        "boredom": 20.0,
        "energy": 95.0,
        "rest": 5.0,
        "safety": 100.0,
        "owner_proximity": 0.0,
        "exploration": 40.0,
    }
    merged.update(scores)
    return {"ok": True, "dominant_need": "balance", "recommended_goal": "calm_idle", "confidence": 0.55, "scores": merged, "reasons": {}}


def shadow(need, goal, priority="normal", confidence=0.90):
    return {"ok": True, "available": True, "recommended_need": need, "recommended_goal": goal, "priority": priority, "confidence": confidence, "top_item": {"name": need}}


def test_social_memory_can_bias_near_threshold_need():
    out = MemoryNeedsBias().apply(base_needs(social=56.0), shadow("social", "seek_owner_or_invite_interaction"), now=10.0)
    assert out["memory_bias"]["applied"] is True
    assert out["dominant_need"] == "social"
    assert out["recommended_goal"] == "seek_owner_or_invite_interaction"


def test_object_memory_can_bias_exploration_near_threshold():
    out = MemoryNeedsBias().apply(base_needs(exploration=55.0), shadow("exploration", "look_around_and_learn", confidence=0.85), now=10.0)
    assert out["memory_bias"]["applied"] is True
    assert out["dominant_need"] == "exploration"
    assert out["recommended_goal"] == "look_around_and_learn"


def test_hazard_memory_uses_guarded_safety_override():
    out = MemoryNeedsBias().apply(base_needs(), shadow("safety", "pause_and_observe", priority="critical", confidence=0.93), now=10.0)
    assert out["memory_bias"]["applied"] is True
    assert out["scores"]["safety"] <= 45.0
    assert out["dominant_need"] == "safety"
    assert out["recommended_goal"] == "pause_and_observe"


def test_low_confidence_memory_is_not_applied():
    out = MemoryNeedsBias().apply(base_needs(social=56.0), shadow("social", "seek_owner_or_invite_interaction", confidence=0.30), now=10.0)
    assert out["memory_bias"]["applied"] is False
    assert out["memory_bias"]["reason"] == "memory_confidence_low"
    assert out["dominant_need"] == "balance"


def test_balance_memory_is_annotation_only():
    out = MemoryNeedsBias().apply(base_needs(), shadow("balance", "calm_idle", priority="low", confidence=0.8), now=10.0)
    assert out["memory_bias"]["applied"] is False
    assert out["memory_bias"]["reason"] == "balance_annotate_only"
    assert out["dominant_need"] == "balance"
