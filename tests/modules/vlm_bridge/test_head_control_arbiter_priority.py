"""Comprehensive unit tests for HeadControlArbiter multi-source arbitration."""
from __future__ import annotations

import time
import pytest
from modules.vlm_bridge.services.head_control_arbiter import HeadControlArbiter, HeadCommand


def test_head_arbiter_priority_locking():
    arb = HeadControlArbiter({"max_rate_hz": 500.0, "deadband_deg": 0.1})
    moves = []
    arb.set_move_callback(lambda p, t: moves.append((p, t)))

    # Lock source to owner_follow (priority 85)
    arb.lock_source("owner_follow", duration_s=10.0)

    # Lower priority request (autonomy, priority 30) should be blocked by source lock
    low_res = arb.request_move(HeadCommand(pan=80.0, tilt=90.0, source="autonomy", priority=30))
    assert low_res.get("ok") is False
    assert low_res.get("reason") == "source_locked"

    # Higher or equal priority (manual, priority 100) should be accepted
    high_res = arb.request_move(HeadCommand(pan=120.0, tilt=90.0, source="manual", priority=100))
    assert high_res.get("ok") is True
    time.sleep(0.005)

    # Owner follow itself should be accepted
    owner_res = arb.request_move(HeadCommand(pan=70.0, tilt=90.0, source="owner_follow", priority=85))
    assert owner_res.get("ok") is True
    time.sleep(0.005)

    # Unlock
    arb.unlock()
    unlocked_res = arb.request_move(HeadCommand(pan=90.0, tilt=90.0, source="autonomy", priority=30))
    assert unlocked_res.get("ok") is True


def test_head_arbiter_clamping():
    arb = HeadControlArbiter({"min_pan": 35, "max_pan": 145, "min_tilt": 65, "max_tilt": 125, "max_rate_hz": 500.0, "deadband_deg": 0.1})
    moves = []
    arb.set_move_callback(lambda p, t: moves.append((p, t)))

    # Request out of bounds
    arb.request_move(HeadCommand(pan=180.0, tilt=10.0, source="manual", priority=100))
    assert moves
    last_pan, last_tilt = moves[-1]
    assert 35 <= last_pan <= 145
    assert 65 <= last_tilt <= 125
