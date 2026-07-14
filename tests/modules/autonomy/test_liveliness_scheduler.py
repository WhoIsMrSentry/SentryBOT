"""Mood-driven liveliness scheduler (timing + change detection + base plan)."""

from __future__ import annotations

from modules.autonomy.services.liveliness import LivelinessScheduler


def test_plan_amplitude_scales_with_energy():
    s = LivelinessScheduler({"amplitude_deg": 5.0})
    low = s.plan(energy=0)["amplitude_deg"]
    high = s.plan(energy=100)["amplitude_deg"]
    assert high > low
    assert s.plan(energy=50)["mode"] == "breathe"


def test_amplitude_is_clamped_to_max():
    s = LivelinessScheduler({"amplitude_deg": 100.0, "max_amplitude_deg": 12.0})
    assert s.plan(energy=100)["amplitude_deg"] <= 12.0


def test_due_on_first_plan_then_throttles():
    s = LivelinessScheduler({"refresh_interval_s": 20.0})
    p = s.plan(energy=50)
    assert s.due(now=100.0, params=p) is True  # nothing sent yet
    s.mark_sent(100.0, p)
    # same params, within refresh window -> not due
    assert s.due(now=105.0, params=p) is False
    # after refresh interval -> due again
    assert s.due(now=121.0, params=p) is True


def test_due_when_params_change_meaningfully():
    s = LivelinessScheduler()
    p1 = s.plan(energy=10)
    s.mark_sent(100.0, p1)
    p2 = s.plan(energy=100)  # much larger amplitude
    assert s.due(now=101.0, params=p2) is True


def test_disabled_never_due():
    s = LivelinessScheduler({"enabled": False})
    p = s.plan(energy=50)
    assert s.due(now=100.0, params=p) is False
