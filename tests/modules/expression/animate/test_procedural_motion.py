import pytest
from modules.expression.animate.services.procedural_motion import ProceduralMotionEngine

def test_procedural_motion_breathing():
    engine = ProceduralMotionEngine(base_pan=90.0, base_tilt=90.0, breathing_period_s=4.0)
    
    # At t=0, sin(0) = 0 -> tilt = 90.0
    m0 = engine.compute_motion(current_time_s=0.0)
    assert m0["tilt"] == 90.0
    assert "ears" in m0
    
    # At t=1.0 (quarter cycle), sin(pi/2) = 1.0 -> tilt = 91.8
    m1 = engine.compute_motion(current_time_s=1.0)
    assert m1["tilt"] == 91.8

    # At t=3.0 (three quarter cycle), sin(3pi/2) = -1.0 -> tilt = 88.2
    m3 = engine.compute_motion(current_time_s=3.0)
    assert m3["tilt"] == 88.2
