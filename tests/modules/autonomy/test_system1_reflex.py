import pytest
from modules.autonomy.services.system1_reflex import System1ReflexEngine, THINKING_FILLERS_TR

def test_system1_body_pose():
    engine = System1ReflexEngine(language="tr")
    pose = engine.get_thinking_body_pose()
    assert "head" in pose
    assert "ears" in pose
    assert "eyes" in pose
    assert pose["eyes"]["name"] == "thinking"
    assert pose["head"]["tilt"] > 90

def test_system1_verbal_filler():
    engine = System1ReflexEngine(language="tr")
    assert not engine.should_emit_verbal_filler(wait_elapsed_s=0.5)
    assert engine.should_emit_verbal_filler(wait_elapsed_s=1.5)
    filler = engine.get_verbal_filler()
    assert filler in THINKING_FILLERS_TR
    # Cooldown prevents immediate repeat
    assert not engine.should_emit_verbal_filler(wait_elapsed_s=1.5)
