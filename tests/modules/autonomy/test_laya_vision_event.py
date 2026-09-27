from types import SimpleNamespace

from modules.autonomy.services.brain_parts.decision import DecisionMixin


class _Mood:
    def __init__(self):
        self.events = []

    def apply_affective_event(self, event):
        self.events.append(event)


class _Laya:
    enabled = True
    _is_available = True

    def __init__(self, affect="user_rude", confidence=0.95):
        self.affect = affect
        self.confidence = confidence
        self.calls = 0

    def decide_with_context(self, text, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            affective_event=self.affect,
            affect_confidence=self.confidence,
            target_module="camera",
            module_confidence=0.9,
            urgency_score=0.0,
        )


def _brain(affect="user_rude", confidence=0.95):
    brain = DecisionMixin()
    brain.config = {"tri_layer": {"laya": {"affective": {
        "vision_event_min_confidence": 0.8,
        "vision_event_min_affect_confidence": 0.8,
        "vision_event_cooldown_s": 60,
    }}}}
    brain.state = {}
    brain._laya_vision_event_lock = __import__("threading").Lock()
    brain.laya_engine = _Laya(affect, confidence)
    brain.mood = _Mood()
    return brain


def test_confident_face_emotion_routes_through_laya_and_updates_mood():
    brain = _brain()
    payload = {"name": "Emir", "emotion": "angry", "confidence": 0.93}

    assert brain.handle_laya_vision_event("face_emotion", payload) is True
    assert brain.mood.events == ["user_rude"]
    assert brain.laya_engine.calls == 1
    assert brain.state["laya_last_vision_affect"]["emotion"] == "angry"


def test_face_emotion_event_rejects_low_confidence_and_deduplicates():
    brain = _brain()
    low = {"name": "Emir", "emotion": "angry", "confidence": 0.6}
    assert brain.handle_laya_vision_event("face_emotion", low) is False
    assert brain.laya_engine.calls == 0

    payload = {"name": "Emir", "emotion": "angry", "confidence": 0.93}
    assert brain.handle_laya_vision_event("face_emotion", payload) is True
    assert brain.handle_laya_vision_event("face_emotion", payload) is False
    assert brain.mood.events == ["user_rude"]


def test_laya_vision_event_requires_confident_affect_classification():
    brain = _brain(affect="user_praise", confidence=0.5)
    payload = {"name": "Emir", "emotion": "happy", "confidence": 0.93}

    assert brain.handle_laya_vision_event("face_emotion", payload) is False
    assert brain.mood.events == []


def test_scene_event_is_classified_once_and_stored_without_direct_mood_delta():
    brain = _brain(affect="neutral", confidence=0.95)
    payload = {
        "reason": "scene_refresh",
        "context": {"summary": "Mutfakta yerde bir kutu görünüyor"},
    }

    assert brain.handle_laya_vision_event("scene_changed", payload) is True
    assert brain.handle_laya_vision_event("scene_changed", payload) is False
    assert brain.laya_engine.calls == 1
    assert brain.mood.events == []
    assert brain.state["laya_last_vision_decision"]["event_type"] == "scene_changed"


def test_non_face_vision_events_do_not_duplicate_perception_mood_appraisal():
    for event_type, payload in (
        ("owner_seen", {"name": "Emir", "confidence": 0.95}),
        ("new_person", {"name": "Guest", "confidence": 0.9}),
        ("hazard_detected", {"hazards": ["obstacle"], "confidence": 0.99}),
    ):
        brain = _brain(affect="user_rude", confidence=0.99)

        assert brain.handle_laya_vision_event(event_type, payload) is True
        assert brain.state["laya_last_vision_decision"]["event_type"] == event_type
        # Existing perception/needs/appraisal owners handle these semantics.
        assert brain.mood.events == []
