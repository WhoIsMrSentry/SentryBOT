"""Tests for idle ambient Pip playlist."""
from __future__ import annotations

import time

from modules.visual_output.oled_faces.services.idle_ambient import IdleAmbientPlayer


def test_idle_ambient_draws_from_pool():
    player = IdleAmbientPlayer(
        {
            "idle_ambient": {
                "enabled": True,
                "min_interval_s": 0.0,
                "max_interval_s": 0.0,
                "hold_s": 1.0,
                "pool": [
                    {"mode": "bitmap", "name": "smoking"},
                    {"mode": "animation", "name": "thinking"},
                ],
            }
        }
    )
    first = player.maybe_action(blocked=False)
    assert first is not None
    assert first.name in {"smoking", "thinking"}
    second = player.maybe_action(blocked=False)
    assert second is None
    time.sleep(1.05)
    third = player.maybe_action(blocked=False)
    assert third is not None


def test_idle_ambient_respects_blocked():
    player = IdleAmbientPlayer({"idle_ambient": {"enabled": True, "min_interval_s": 0.0, "max_interval_s": 0.0}})
    assert player.maybe_action(blocked=True) is None
