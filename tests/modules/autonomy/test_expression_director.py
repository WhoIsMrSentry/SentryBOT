"""Tests for the multi-modal expression director and idle micro-behaviors."""

from __future__ import annotations

from modules.autonomy.services.expression_director import ExpressionDirector
from modules.autonomy.services.brain_parts.animations import AnimationSupportMixin


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def set_expression_event(self, event_type, data=None):
        self.calls.append(("expression_event", event_type, data))

    def speak_preferred(self, text, tone=None, language=None):
        self.calls.append(("speak_preferred", text, tone))

    def push_interaction_event(self, event_type, data=None):
        self.calls.append(("event", event_type))

    def move_head(self, pan, tilt, speed=0.8):
        self.calls.append(("head", pan, tilt))

    def oled_show(self, name):
        self.calls.append(("eyes", name))

    def set_neopixel(self, effect, emotions=None, color=None, duration=None):
        self.calls.append(("leds", effect, tuple(emotions or []), tuple(color or ())))

    def emote_neopixel(self, emotions, duration=0.25):
        self.calls.append(("emote", tuple(emotions or ()), duration))
        return {"ok": True}

    def kinds(self):
        return [c[0] for c in self.calls]


def test_express_fires_all_modalities_with_canonical_label():
    client = _RecordingClient()
    director = ExpressionDirector(client)
    canon = director.express("happy", say="merhaba", move_head=(100, 90))
    assert canon == "happy"  # new implementation returns the emotion as-is
    kinds = client.kinds()
    assert {"expression_event", "speak_preferred"} <= set(kinds)
    expr = next(c for c in client.calls if c[0] == "expression_event")
    assert expr[1] == "emotion:happy"
    assert expr[2]["attention"] == "user"
    assert expr[2]["head_hint"] == {"pan": 100, "tilt": 90}
    voice = next(c for c in client.calls if c[0] == "speak_preferred")
    assert voice[2] == "happy"


def test_express_without_speech_or_head_skips_those():
    client = _RecordingClient()
    director = ExpressionDirector(client)
    director.express("anger")
    kinds = set(client.kinds())
    assert "speak_preferred" not in kinds
    assert {"expression_event"} <= kinds


def test_failing_modality_does_not_block_others():
    class _FlakyClient(_RecordingClient):
        def set_expression_event(self, event_type, data=None):
            raise RuntimeError("Expression bus down")
            
    client = _FlakyClient()
    director = ExpressionDirector(client)
    # Even if expression event fails, speech should still trigger
    director.express("joy", say="still talking")
    assert "speak_preferred" in client.kinds()


class _StubMood:
    def get_body_language_profile(self):
        return {"pan_delta": 4, "tilt_delta": 3, "event": "autonomy.neutral"}

    def get_dominant_emotion(self):
        return "joy"


class _Mini(AnimationSupportMixin):
    def __init__(self, client):
        self.client = client
        self.state = {"current_pan": 90, "current_tilt": 90}
        self.mood = _StubMood()


def test_eye_saccade_emits_gesture_interaction_event():
    client = _RecordingClient()
    mini = _Mini(client)
    mini._perform_eye_saccade()
    gestures = [c for c in client.calls if c[0] == "event" and c[1].startswith("gesture:")]
    assert gestures
    gaze = gestures[0][1].removeprefix("gesture:")
    assert gaze in {
        "look_left",
        "look_right",
        "look_up",
        "look_down",
        "wink",
        "wink_left",
        "wink_right",
        "blink",
        "double_blink",
    }


def test_ear_micromovement_emits_emotion_event():
    client = _RecordingClient()
    mini = _Mini(client)
    mini._perform_ear_micromovement()
    assert ("event", "emotion:joy") in client.calls
