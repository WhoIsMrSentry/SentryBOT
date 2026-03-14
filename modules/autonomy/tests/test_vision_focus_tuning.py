from __future__ import annotations

from modules.autonomy.services.brain_parts.vision import VisionMixin


class _FocusClient:
    def __init__(self):
        self.moves = []
        self.events = []

    def push_interaction_event(self, event_type, data=None):
        self.events.append((event_type, data))

    def move_head(self, pan, tilt):
        self.moves.append((int(pan), int(tilt)))


class _FocusBrain(VisionMixin):
    def __init__(self):
        self.client = _FocusClient()
        self._vision_cfg = {
            "focus": {"jitter_min": 1, "jitter_max": 1, "deadband_deg": 2, "smoothing": 0.5},
            "dynamic_cooldown": {"enabled": True, "near_distance_m": 1.2, "far_distance_m": 3.0, "near_multiplier": 0.6, "far_multiplier": 1.3},
            "person_cooldown_s": 20,
        }
        self.owner_cfg = {}
        self.state = {"current_pan": 90, "current_tilt": 90}

    def _trigger_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> bool:
        return False

    def _blink_fallback(self):
        return None

    def _is_owner_name(self, name: str | None) -> bool:
        return str(name or "").lower() == "owner"


def test_focus_deadband_skips_tiny_motion():
    brain = _FocusBrain()
    brain._focus_on_target({"label": "person"})
    assert brain.client.moves == []


def test_focus_moves_when_over_deadband():
    brain = _FocusBrain()
    brain._vision_cfg["focus"] = {"jitter_min": 4, "jitter_max": 4, "deadband_deg": 2, "smoothing": 0.5}
    brain._focus_on_target({"label": "person"})
    assert len(brain.client.moves) == 1
    # with smoothing=0.5 and proposed 94 from 90, expected rounded 92
    assert brain.client.moves[0][0] == 92


def test_dynamic_cooldown_uses_distance_bands():
    brain = _FocusBrain()
    assert brain._compute_person_cooldown({"distance_m": 0.8}) == 12.0
    assert brain._compute_person_cooldown({"distance_m": 3.5}) == 26.0
    assert brain._compute_person_cooldown({"distance_m": 2.0}) == 20.0


def test_scene_picker_prefers_owner_then_close_variants():
    brain = _FocusBrain()
    assert brain._pick_vision_scene("owner", {"distance_m": 2.0}) == "vision_greeting_owner"
    assert brain._pick_vision_scene("Unknown", {"distance_m": 0.9}) == "vision_greeting_unknown_close"
    assert brain._pick_vision_scene("Ali", {"distance_m": 0.9}) == "vision_greeting_known_close"
