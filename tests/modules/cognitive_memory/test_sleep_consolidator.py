import pytest
from modules.cognitive_memory.services.sleep_consolidator import SleepConsolidator

def test_ebbinghaus_retention():
    sc = SleepConsolidator()
    # At t=0, retention is 100%
    assert sc.compute_ebbinghaus_retention(1.0, elapsed_hours=0) == 1.0
    # After 24 hours with stability 24, retention is e^(-1) ~ 0.368
    r24 = sc.compute_ebbinghaus_retention(1.0, elapsed_hours=24, stability=24.0)
    assert 0.35 <= r24 <= 0.38
    # After 72 hours, it decays further
    r72 = sc.compute_ebbinghaus_retention(1.0, elapsed_hours=72, stability=24.0)
    assert r72 < r24

def test_consolidate_session():
    sc = SleepConsolidator()
    now = 1000000.0
    interactions = [
        {"user": "Emir", "text": "Bugün hava çok güzel.", "importance": 2.0, "timestamp": now - 3600},
        {"user": "Emir", "text": "Işıkları kapat.", "importance": 0.5, "timestamp": now - 86400}, # 24 saat önce, önemsiz
    ]
    res = sc.consolidate_session(interactions, current_time_s=now)
    assert res["ok"]
    assert res["consolidated_count"] >= 1
    assert "Emir" in res["user_interactions"]
