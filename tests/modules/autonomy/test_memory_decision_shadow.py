from modules.autonomy.services.memory_decision_shadow import MemoryDecisionShadow


def eval_one(item):
    return MemoryDecisionShadow().evaluate({"total": 1, "recent": [item]}, [item], now=100.0)


def test_safety_has_highest_priority():
    result = eval_one({"kind": "events", "name": "hazard", "summary": "obstacle close", "tags": ["safety"], "confidence": 0.8, "salience": 0.9, "last_seen_ts": 99.0})
    assert result["available"] is True
    assert result["recommended_need"] == "safety"
    assert result["recommended_goal"] == "pause_and_observe"
    assert result["priority"] == "critical"
    assert result["apply_to_needs"] is False


def test_owner_memory_suggests_social_shadow():
    result = eval_one({"kind": "people", "name": "owner", "summary": "owner heard nearby", "tags": ["owner"], "confidence": 0.8, "last_seen_ts": 99.0})
    assert result["recommended_need"] == "social"
    assert result["recommended_goal"] == "seek_owner_or_invite_interaction"


def test_object_memory_suggests_exploration_shadow():
    result = eval_one({"kind": "objects", "name": "unknown object", "summary": "new object on desk", "tags": ["novel"], "confidence": 0.75, "last_seen_ts": 99.0})
    assert result["recommended_need"] == "exploration"
    assert result["recommended_goal"] == "look_around_and_learn"


def test_quiet_memory_suggests_balance_shadow():
    result = eval_one({"kind": "observations", "name": "stable quiet room", "summary": "stable quiet room", "tags": ["stable"], "confidence": 0.6, "last_seen_ts": 99.0})
    assert result["recommended_need"] == "balance"
    assert result["recommended_goal"] == "calm_idle"
