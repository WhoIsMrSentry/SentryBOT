from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from modules.autonomy.services.brain_parts.responses import ResponseTagMixin


class DummyClient:
    def __init__(self) -> None:
        self.head_moves: list[tuple[int, int]] = []
        self.neopixel_fills: list[tuple[int, int, int]] = []
        self.neopixel_modes: list[str] = []
        self.events: list[tuple[str, Dict[str, Any] | None]] = []

    def move_head(self, pan: int, tilt: int) -> None:
        self.head_moves.append((int(pan), int(tilt)))

    def fill_neopixel_color(self, r: int, g: int, b: int) -> None:
        self.neopixel_fills.append((r, g, b))

    def set_neopixel(self, effect: str) -> None:
        self.neopixel_modes.append(effect)

    def push_interaction_event(self, event_type: str, data: Dict[str, Any] | None = None) -> None:
        self.events.append((event_type, data))


class DummyBrain(ResponseTagMixin):
    def __init__(self) -> None:
        self.client = DummyClient()
        self.state = {"current_pan": 90, "current_tilt": 90}
        self.config = {
            "lights": {
                "default_mode": "breathe",
                "palettes": {"custom": [10, 20, 30]},
            }
        }
        self.animation_available = True
        self.scan_fallbacks = 0

    def _trigger_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> bool:
        return self.animation_available

    def _head_scan_fallback(self) -> None:
        self.scan_fallbacks += 1


def test_action_bundle_dispatches_blocks() -> None:
    brain = DummyBrain()
    bundle = {
        "commands": ["head_nod"],
        "blocks": [
            {"type": "lights", "attrs": {"palette": "calm_violet", "intensity": 0.5, "mode": "pulse"}},
            {"type": "servo", "attrs": {"pan": 105, "tilt": 90}},
            {"type": "anim", "attrs": {"name": "look_around", "speed": 1.2}},
            {"type": "event", "attrs": {"type": "comfort.touch", "level": 0.8}},
            {"type": "mode", "attrs": {"name": "Comfort", "reason": "user_sad"}},
        ],
    }
    text = brain._handle_llm_actions("Selam", bundle)
    assert text == "Selam"
    assert brain.client.neopixel_fills[-1] == (60, 40, 127)
    assert brain.client.neopixel_modes[-1] == "pulse"
    assert brain.client.head_moves[-1] == (105, 90)
    assert any(evt[0] == "persona.mode" for evt in brain.client.events)


def test_inline_tags_are_parsed_when_bundle_missing() -> None:
    brain = DummyBrain()
    brain.animation_available = False
    result = brain._handle_llm_actions("Merhaba [cmd:head_left] [[servo pan=120 tilt=100]]", action_bundle=None)
    assert result == "Merhaba"
    assert brain.client.head_moves[-1] == (120, 100)
