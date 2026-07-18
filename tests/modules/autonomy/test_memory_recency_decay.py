from modules.autonomy.services.memory_decision_shadow import MemoryDecisionShadow

NOW = 1000.0


def item(kind, name, summary, tags=None, last_seen_ts=None, confidence=0.85, salience=0.85, source="probe"):
    return {
        "kind": kind,
        "name": name,
        "summary": summary,
        "tags": tags or [],
        "confidence": confidence,
        "salience": salience,
        "source": source,
        "last_seen_ts": last_seen_ts,
    }


def eval_items(*items):
    return MemoryDecisionShadow().evaluate({"total": len(items), "recent": list(items)}, list(items), now=NOW)


def test_fresh_hazard_can_influence_safety():
    result = eval_items(item("events", "hazard", "possible obstacle", ["safety"], NOW - 5))
    assert result["available"] is True
    assert result["recommended_need"] == "safety"
    assert result["priority"] == "critical"
    assert result["stale_count"] == 0


def test_stale_hazard_does_not_lock_safety():
    result = eval_items(item("events", "hazard", "possible obstacle", ["safety"], NOW - 120))
    assert result["available"] is False
    assert result["reason"] == "memory_hints_stale"
    assert result["stale_count"] == 1
    assert result["stale"][0]["need"] == "safety"


def test_fresh_object_can_influence_exploration():
    result = eval_items(item("objects", "unknown object", "new object on desk", ["novel"], NOW - 30, confidence=0.75))
    assert result["available"] is True
    assert result["recommended_need"] == "exploration"
    assert result["recommended_goal"] == "look_around_and_learn"


def test_stale_object_is_ignored_after_age_limit():
    result = eval_items(item("objects", "unknown object", "new object on desk", ["novel"], NOW - 400, confidence=0.75))
    assert result["available"] is False
    assert result["reason"] == "memory_hints_stale"
    assert result["stale_count"] == 1


def test_quiet_memory_has_longer_balance_window():
    result = eval_items(item("observations", "stable quiet room", "stable quiet room", ["stable"], NOW - 300, confidence=0.65))
    assert result["available"] is True
    assert result["recommended_need"] == "balance"


def test_very_old_quiet_memory_is_stale():
    result = eval_items(item("observations", "stable quiet room", "stable quiet room", ["stable"], NOW - 900, confidence=0.65))
    assert result["available"] is False
    assert result["stale_count"] == 1
