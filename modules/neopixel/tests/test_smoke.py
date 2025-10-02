from __future__ import annotations

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
