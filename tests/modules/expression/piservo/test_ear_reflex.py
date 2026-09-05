import pytest
from modules.expression.piservo.services.ear_reflex import EarReflexEngine

def test_ear_reflex_left():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=-45.0, energy=1.0)
    assert angles.left < 90.0  # Left ear perked up
    assert angles.right >= 90.0

def test_ear_reflex_right():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=50.0, energy=1.0)
    assert angles.right < 90.0  # Right ear perked up
    assert angles.left >= 90.0

def test_ear_reflex_front_sudden():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=0.0, energy=1.0)
    assert angles.left < 90.0
    assert angles.right < 90.0
    assert angles.left == angles.right
