from __future__ import annotations

from modules.expression.interactions.services.engine import InteractionEngine


class _CompanionNeo:
    def __init__(self) -> None:
        self.modes: list[str] = []
        self.eye_colors = []

    def companion_mode(self, mode: str, eye_color=None) -> None:
        self.modes.append(str(mode))
        self.eye_colors.append(eye_color)

    def companion_is_active(self) -> bool:
        return bool(self.modes) and self.modes[-1] not in {"", "off"}


def _engine_with_companion_rules() -> InteractionEngine:
    cfg = {
        "rules": [
            {
                "id": "wakeword_detected",
                "when": {"event": "wakeword.detected"},
                "action": {"companion": {"mode": "wake_spin", "eye_color": "#30E3CA"}},
                "priority": "critical",
            },
            {
                "id": "agent_processing_start",
                "when": {"event": "agent.processing.start"},
                "action": {"companion": {"mode": "thinking"}},
                "priority": "high",
            },
        ],
        "defaults": {"idle": {"base": {"name": "BREATHE", "color": "#30E3CA"}}},
    }
    eng = InteractionEngine(cfg, neo_client=None)
    eng.neo = _CompanionNeo()
    return eng


def test_push_event_dispatches_companion_immediately():
    eng = _engine_with_companion_rules()
    eng.push_event("wakeword.detected", {"wakeword": "hey mycroft"})
    assert eng.neo.modes == ["wake_spin"]
    assert eng.neo.eye_colors == ["#30E3CA"]


def test_push_event_dispatches_agent_processing_companion():
    eng = _engine_with_companion_rules()
    eng.push_event("agent.processing.start", None)
    assert eng.neo.modes == ["thinking"]


def test_companion_event_is_not_dispatched_again_on_tick():
    eng = _engine_with_companion_rules()
    eng.push_event("wakeword.detected", {"wakeword": "hey mycroft"})
    eng._tick()
    assert eng.neo.modes == ["wake_spin"]
    assert "event" not in eng.get_state()["ctx"]



def test_via_expression_skips_direct_neopixel_companion():
    eng = _engine_with_companion_rules()
    eng._via_expression = True
    seen = []
    eng.register_event_handler(lambda event, data: seen.append(event))
    eng.push_event("wakeword.detected", {"wakeword": "hey sentry"})
    assert eng.neo.modes == []
    assert "wakeword.detected" in seen
