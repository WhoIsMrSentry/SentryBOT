import pytest
from modules.autonomy.services.saliency_map import SaliencyMapEngine

def test_saliency_owner_priority():
    engine = SaliencyMapEngine()
    # Owner face vs motion vector
    target = engine.evaluate(
        faces=[{"name": "Emir", "is_owner": True, "center_x": 0.5}],
        motion={"active": True, "pan": 110, "tilt": 90},
    )
    assert target.target_type == "person"
    assert target.label == "Emir"
    assert target.priority_score == 1.0

def test_saliency_sound_over_motion():
    engine = SaliencyMapEngine()
    target = engine.evaluate(
        sound_event={"detected": True, "energy": 0.9, "angle": 30.0},
        motion={"active": True, "pan": 45, "tilt": 90},
    )
    assert target.target_type == "sound"
    assert target.pan_hint == 120

def test_saliency_idle():
    engine = SaliencyMapEngine()
    target = engine.evaluate()
    assert target.target_type == "idle"
    assert target.pan_hint == 90
