"""Emotion-aware shaping of liveliness amplitude / tempo / mode."""

from __future__ import annotations

from modules.autonomy.services.liveliness import LivelinessScheduler


def test_excited_is_bigger_and_faster_than_tired():
    s = LivelinessScheduler({"amplitude_deg": 5.0, "max_amplitude_deg": 30.0})
    excited = s.plan(energy=80, dominant_emotion="excitement")
    tired = s.plan(energy=80, dominant_emotion="tired")
    assert excited["amplitude_deg"] > tired["amplitude_deg"]
    assert excited["period_ms"] < tired["period_ms"]  # faster


def test_anger_uses_micro_mode():
    s = LivelinessScheduler()
    assert s.plan(energy=60, dominant_emotion="anger")["mode"] == "micro"


def test_alias_resolves_same_as_canonical():
    s = LivelinessScheduler()
    assert s.plan(energy=50, dominant_emotion="happy") == s.plan(energy=50, dominant_emotion="joy")


def test_neutral_keeps_breathe_mode():
    s = LivelinessScheduler()
    assert s.plan(energy=50, dominant_emotion="neutral")["mode"] == "breathe"


def test_period_stays_within_bounds():
    s = LivelinessScheduler({"period_ms": 4500})
    for emo in ("furious", "tired", "neutral", "fear", "sadness"):
        p = s.plan(energy=50, dominant_emotion=emo)["period_ms"]
        assert 800 <= p <= 12000
