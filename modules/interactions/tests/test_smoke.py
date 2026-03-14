from __future__ import annotations

import time

from modules.interactions.xInteractionsService import xInteractionsService
from modules.interactions.services.engine import InteractionEngine


def test_smoke():
    svc = xInteractionsService()
    svc.start()
    state = svc.engine.get_state()
    assert "metrics" in state
    svc.stop()


class _FakeNeo:
    def __init__(self) -> None:
        self.effects = []

    def set_base(self, name, color=None, speed=None):
        return None

    def play_effect(self, name, duration_ms=800, color=None):
        self.effects.append((str(name), int(duration_ms), color))


def _make_engine(cfg_override=None) -> InteractionEngine:
    cfg = {
        "tick_interval_ms": 5,
        "thresholds": {"cpu_load": {"window_s": 60}},
        "adapter": {"http_base_url": ""},
        "defaults": {"idle": {"base": {"name": "BREATHE", "color": "#000000"}}},
        "rules": [{
            "id": "speech_start",
            "when": {"event": "speech.start"},
            "action": {"effect": {"name": "RAINBOW_CYCLE", "duration_ms": 20}},
            "priority": "high",
        }],
    }
    if cfg_override:
        cfg.update(cfg_override)
    eng = InteractionEngine(cfg)
    eng.neo = _FakeNeo()
    return eng


def test_manual_effect_works_without_rule():
    eng = _make_engine({"rules": []})
    eng.trigger_effect("COMET", 20)
    eng._tick()
    time.sleep(0.05)
    assert eng.neo.effects and eng.neo.effects[0][0] == "COMET"


def test_quiet_hours_suppresses_non_allowed_effects():
    eng = _make_engine({
        "quiet_hours": {
            "enabled": True,
            "start": "00:00",
            "end": "23:59",
            "suppress_effects": True,
            "allow_events": ["error"],
        }
    })
    eng._is_quiet_hours_active = lambda: True  # type: ignore[assignment]
    eng.push_event("speech.start", None)
    eng._tick()
    time.sleep(0.05)
    assert eng.neo.effects == []
