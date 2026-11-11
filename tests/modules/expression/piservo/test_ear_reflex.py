import modules.expression.piservo.services.ear_reflex as ear_reflex_mod
from modules.expression.piservo.services.ear_reflex import EarReflexEngine


def test_ear_reflex_left():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=-45.0, energy=1.0)
    assert angles is not None
    assert angles.left < 90.0  # Left ear perked up
    assert angles.right >= 90.0


def test_ear_reflex_right():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=50.0, energy=1.0)
    assert angles is not None
    assert angles.right < 90.0  # Right ear perked up
    assert angles.left >= 90.0


def test_ear_reflex_front_sudden():
    engine = EarReflexEngine()
    angles = engine.compute_reflex(doa_angle_deg=0.0, energy=1.0)
    assert angles is not None
    assert angles.left < 90.0
    assert angles.right < 90.0
    assert angles.left == angles.right


def test_ear_reflex_cooldown_and_neutral_offsets(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(ear_reflex_mod.time, "monotonic", lambda: clock[0])

    engine = EarReflexEngine(neutral_left=85.0, neutral_right=95.0, cooldown_s=0.4)
    first = engine.compute_reflex(doa_angle_deg=-40.0, energy=1.0)
    assert first is not None

    # Inside cooldown: must return None so active twitch is not cancelled back to neutral
    clock[0] = 100.2
    assert engine.compute_reflex(doa_angle_deg=40.0, energy=1.0) is None

    # After cooldown expires: fires again
    clock[0] = 100.5
    second = engine.compute_reflex(doa_angle_deg=40.0, energy=1.0)
    assert second is not None
    assert second.right < 95.0

    # Vigilance & relax helpers use configured neutrals cleanly
    vig_l, vig_r = engine.compute_vigilance()
    rel_l, rel_r = engine.compute_relax()
    assert vig_l == 60.0 and vig_r == 70.0
    assert (rel_l, rel_r) == (85.0, 95.0)
