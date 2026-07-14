from __future__ import annotations

from modules.autonomy.services.brain_parts.scenes import SceneMixin


class _FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def push_interaction_event(self, event_type, data=None):
        self.calls.append(("event", event_type, data))

    def set_interaction_effect(self, name, duration_ms=800, force=False):
        self.calls.append(("effect", name, int(duration_ms), bool(force)))

    def set_interaction_base(self, name, color=None):
        self.calls.append(("base", name, color))

    def move_head(self, pan, tilt):
        self.calls.append(("head", int(pan), int(tilt)))

    def fill_neopixel_segment_color(self, segment, r, g, b):
        self.calls.append(("segment_fill", str(segment), int(r), int(g), int(b)))

    def set_neopixel_segment_effect(self, segment, effect, color=None, emotions=None, iterations=None):
        self.calls.append(("segment_anim", str(segment), str(effect), color, emotions, iterations))

    def apply_neopixel_preset(self, name):
        self.calls.append(("preset", str(name)))


class _FakeBrain(SceneMixin):
    def __init__(self):
        self.client = _FakeClient()
        self.state = {"current_pan": 90, "current_tilt": 90}
        self.config = {
            "scenes": {
                "vision_greeting_known": {
                    "steps": [
                        {"type": "event", "name": "scene.start"},
                        {"type": "preset", "name": "owner_welcome"},
                        {"type": "effect", "name": "COMET", "duration_ms": 300},
                        {"type": "effect_burst", "name": "COMET", "duration_ms": 120, "count": 2, "interval_ms": 0},
                        {"type": "segment_anim", "segment": "jewel", "name": "PULSE", "color": "#00AAFF", "iterations": 1},
                        {"type": "head", "pan": 100, "tilt": 95},
                        {"type": "speak", "text": "Merhaba {name}", "emotion": "joy"},
                        {"type": "segment_fill", "segment": "stick", "color": [1, 2, 3]},
                        {"type": "base", "name": "BREATHE", "color": "#00AAFF"},
                    ]
                }
            }
        }
        self.spoken = []
        self.anims = []

    def _trigger_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> bool:
        self.anims.append((name, speed, loop))
        return True

    def _speak_with_mood(self, text: str, emotion: str | None = None) -> None:
        self.spoken.append((text, emotion))


def test_scene_runs_all_core_steps():
    b = _FakeBrain()
    ok = b._run_scene("vision_greeting_known", {"name": "Emir"})
    assert ok is True
    assert ("preset", "owner_welcome") in b.client.calls
    assert ("effect", "COMET", 300, False) in b.client.calls
    burst_count = len([c for c in b.client.calls if c[:2] == ("effect", "COMET") and c[2] == 120])
    assert burst_count == 2
    assert any(c[0] == "segment_anim" and c[1] == "jewel" for c in b.client.calls)
    assert ("segment_fill", "stick", 1, 2, 3) in b.client.calls
    assert ("head", 100, 95) in b.client.calls
    assert ("base", "BREATHE", "#00AAFF") in b.client.calls
    assert b.spoken == [("Merhaba Emir", "joy")]


def test_scene_missing_returns_false():
    b = _FakeBrain()
    assert b._run_scene("does_not_exist", {}) is False
