"""Head arbiter accepts sound_direction source at priority 60."""
from __future__ import annotations

from modules.vlm_bridge.services.head_control_arbiter import HeadControlArbiter, HeadCommand


def test_sound_direction_move_accepted():
    moves = []
    arb = HeadControlArbiter({"max_rate_hz": 200.0, "deadband_deg": 0.5})
    arb.set_move_callback(lambda pan, tilt: moves.append((pan, tilt)))
    result = arb.request_move(
        HeadCommand(pan=100.0, tilt=90.0, source="sound_direction", priority=60, ttl_s=2.0)
    )
    assert result.get("ok") is True
    assert moves
