"""Brain liveliness tick forwards mood-shaped motion to the client (gated)."""

from __future__ import annotations

from modules.autonomy.services.brain_parts.animations import AnimationSupportMixin
from modules.autonomy.services.liveliness import LivelinessScheduler


class _Mood:
    def __init__(self, energy=70, dominant="joy"):
        self._energy = energy
        self._dominant = dominant

    def __getitem__(self, key):
        return self._energy if key == "energy" else 50

    def get_dominant_emotion(self):
        return self._dominant


class _Client:
    def __init__(self):
        self.liveliness_calls = []

    def set_liveliness(self, enable, **kwargs):
        self.liveliness_calls.append({"enable": enable, **kwargs})
        return {"ok": True}


class _Brain(AnimationSupportMixin):
    def __init__(self, **state):
        self.client = _Client()
        self.mood = _Mood()
        self.liveliness = LivelinessScheduler({"refresh_interval_s": 20.0})
        self._speech_busy = False
        self.state = state


def test_tick_sends_liveliness_when_due():
    b = _Brain(current_pan=90, current_tilt=95)
    b._liveliness_tick(now=100.0)
    assert len(b.client.liveliness_calls) == 1
    call = b.client.liveliness_calls[0]
    assert call["enable"] is True
    assert call["pan_center"] == 90 and call["tilt_center"] == 95


def test_tick_suppressed_while_speaking():
    b = _Brain()
    b._speech_busy = True
    b._liveliness_tick(now=100.0)
    assert b.client.liveliness_calls == []


def test_tick_suppressed_during_follow_and_sleep():
    b = _Brain(follow_active=True)
    b._liveliness_tick(now=100.0)
    assert b.client.liveliness_calls == []

    b2 = _Brain(is_sleeping=True)
    b2._liveliness_tick(now=100.0)
    assert b2.client.liveliness_calls == []


def test_tick_throttles_repeated_same_params():
    b = _Brain()
    b._liveliness_tick(now=100.0)
    b._liveliness_tick(now=105.0)  # within refresh, same params
    assert len(b.client.liveliness_calls) == 1
