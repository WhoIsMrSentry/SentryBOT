"""Tests for the multi-modal expression director and idle micro-behaviors."""

from __future__ import annotations

from modules.autonomy.services.expression_director import ExpressionDirector
from modules.autonomy.services.brain_parts.animations import AnimationSupportMixin


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def set_neopixel(self, effect, emotions=None, color=None, duration=None):
        self.calls.append(("leds", effect, tuple(emotions or []), tuple(color or ())))

    def emote_neopixel(self, emotions, duration=0.25):
        self.calls.append(("emote", tuple(emotions or ()), duration))
        return {"ok": True}

    def oled_show(self, name):
        self.calls.append(("eyes", name))

    def push_interaction_event(self, event_type, data=None):
        self.calls.append(("event", event_type))

    def move_head(self, pan, tilt, speed=0.8):
        self.calls.append(("head", pan, tilt))

    def speak(self, text, tone=None, engine=None, language=None):
        self.calls.append(("voice", text, tone))

    def kinds(self):
        return [c[0] for c in self.calls]


def test_express_fires_all_modalities_with_canonical_label():
    client = _RecordingClient()
    director = ExpressionDirector(client)
    canon = director.express("happy", say="merhaba", move_head=(100, 90))
    assert canon == "joy"
    kinds = client.kinds()
    assert {"emote", "eyes", "event", "head", "voice"} <= set(kinds)
    emote = next(c for c in client.calls if c[0] == "emote")
    assert emote[1] == ("joy",)
    assert ("event", "emotion:joy") in client.calls
    voice = next(c for c in client.calls if c[0] == "voice")
    assert voice[2] == "joy"  # TTS tone resolved from vocab


def test_express_without_speech_or_head_skips_those():
    client = _RecordingClient()
    director = ExpressionDirector(client)
    director.express("anger")
    kinds = set(client.kinds())
    assert "voice" not in kinds
    assert "head" not in kinds
    assert {"emote", "eyes", "event"} <= kinds


def test_failing_modality_does_not_block_others():
    class _Flaky(_RecordingClient):
        def oled_show(self, name):
            raise RuntimeError("display offline")

    client = _Flaky()
    director = ExpressionDirector(client)
    canon = director.express("surprise")
    assert canon == "surprise"
    # eyes failed, but emote + ears still fired
    assert "emote" in client.kinds()
    assert ("event", "emotion:surprise") in client.calls


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


def test_eye_saccade_uses_gaze_bitmaps():
    client = _RecordingClient()
    mini = _Mini(client)
    mini._perform_eye_saccade()
    eyes = [c for c in client.calls if c[0] == "eyes"]
    assert eyes and eyes[0][1] in {"look_left", "look_right", "look_up", "look_down"}


def test_ear_micromovement_emits_emotion_event():
    client = _RecordingClient()
    mini = _Mini(client)
    mini._perform_ear_micromovement()
    assert ("event", "emotion:joy") in client.calls
