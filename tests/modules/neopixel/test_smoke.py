from __future__ import annotations

import time

from modules.neopixel.services.runner import NeoRunner
from modules.neopixel.services.driver import NeoDriverConfig
from modules.neopixel.emotions.loader import EmotionStore


def test_basic_effects_smoke():
    cfg = NeoDriverConfig(num_leds=5)
    r = NeoRunner(cfg)
    r.clear()
    r.fill(10, 20, 30)
    r.theater_chase(cycles=1, wait=0)
    # emotions
    store = EmotionStore()
    col = store.random_color("joy")
    assert isinstance(col, tuple) and len(col) == 3
    r.emote_sequence(["joy", "fear"], duration=0)


def test_emotion_palette_alias_resolution():
    # Canonical labels and aliases must resolve to a real palette colour
    # instead of the white (255,255,255) fallback.
    store = EmotionStore()
    palette = store.load()
    assert "joy" in palette.entries_by_emotion
    assert "anger" in palette.entries_by_emotion
    # alias 'happy' resolves through the shared vocab to the 'joy' palette
    assert store.random_color("happy") != (255, 255, 255)
    assert store.random_color("scared") != (255, 255, 255)


def test_companion_cancels_running_animation_and_blocks_direct_fill():
    cfg = NeoDriverConfig(num_leds=23)
    companion = {
        "enabled": True,
        "tick_ms": 5,
        "layout": {
            "jewel_start": 0,
            "jewel_count": 7,
            "sticks": [
                {"start": 7, "count": 8, "channel": 0},
                {"start": 15, "count": 8, "channel": 1},
            ],
        },
        "wake_spin": {"duration_ms": 2000, "wait_ms": 5},
    }
    runner = NeoRunner(cfg, companion_cfg=companion)
    assert runner.animate("BREATHE", color=(255, 255, 255)) is True
    generation = runner.companion_status()["animation_generation"]
    assert runner.companion_set_mode("wake_spin") is True
    assert runner.companion_status()["animation_generation"] > generation
    assert runner.fill(255, 0, 255) is False
    time.sleep(0.03)
    assert runner.companion_status()["mode"] in ("wake_spin", "listen_vu")
    runner.stop()


def test_preset_segment_effects_do_not_cancel_each_other():
    cfg = NeoDriverConfig(num_leds=23)
    runner = NeoRunner(
        cfg,
        segments=[
            {"name": "jewel", "start": 0, "count": 7},
            {"name": "stick", "start": 7, "count": 16},
        ],
        presets={
            "dual": {
                "jewel": {"effect": "PULSE", "color": "#FFD700"},
                "stick": {"effect": "COMET", "color": "#00AAFF"},
            }
        },
    )
    calls = []

    def _record(name, **kwargs):
        calls.append((name, kwargs))
        return True

    runner.animate = _record  # type: ignore[method-assign]
    assert runner.apply_preset("dual") is True
    assert [call[0] for call in calls] == ["PULSE", "COMET"]
    assert all(call[1]["coalesce"] is False for call in calls)
