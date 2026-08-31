import pytest
import time
from modules.visual_output.oled_faces.services.eyes.engine import EyeEngine
from modules.visual_output.neopixel.services.animations import emotional_pulse
from modules.visual_output.neopixel.services.driver import NeoDriver, NeoDriverConfig

def test_eye_set_gaze():
    engine = EyeEngine(lambda img: None)
    engine.set_gaze(12.5, -4.0, hold_s=2.0)
    assert engine.look_x == 12.5
    assert engine.look_y == -4.0

def test_biological_blink_frequency():
    engine = EyeEngine(lambda img: None)
    # Excited -> fast blink gap
    engine.mood = "excited"
    now = time.monotonic()
    engine._next_blink = now - 1.0  # Force blink trigger
    engine._step(now, 0.05)
    assert 1.0 <= (engine._next_blink - now) <= 2.6

    # Sleepy -> slow blink gap
    engine.mood = "sleepy"
    engine._blink = None
    now += 5.0
    engine._next_blink = now - 1.0
    engine._step(now, 0.05)
    assert 4.0 <= (engine._next_blink - now) <= 8.6

def test_emotional_pulse_animation():
    driver = NeoDriver(NeoDriverConfig(num_leds=16))
    # Run 1 quick pulse iteration
    emotional_pulse(driver, color=(255, 100, 50), bpm=120.0, iterations=1, wait=0.001)
    assert driver.num_leds == 16

