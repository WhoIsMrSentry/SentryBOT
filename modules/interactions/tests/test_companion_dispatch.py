from __future__ import annotations

from modules.interactions.services.engine import InteractionEngine


class _CompanionNeo:
    def __init__(self) -> None:
        self.modes: list[str] = []
        self.vu_calls: list[tuple[float, float | None]] = []

    def companion_mode(self, mode: str, eye_color=None) -> None:
        self.modes.append(str(mode))

    def companion_vu(self, level: float, right=None) -> None:
        self.vu_calls.append((float(level), None if right is None else float(right)))

    def companion_is_active(self) -> bool:
        return bool(self.modes) and self.modes[-1] not in {"", "off"}


def _engine_with_companion_rules() -> InteractionEngine:
    cfg = {
        "rules": [
            {
                "id": "wakeword_detected",
                "when": {"event": "wakeword.detected"},
                "action": {"companion": {"mode": "wake_spin", "eye_color": "#FFD700"}},
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


def test_push_event_dispatches_agent_processing_companion():
    eng = _engine_with_companion_rules()
    eng.push_event("agent.processing.start", None)
    assert eng.neo.modes == ["thinking"]
