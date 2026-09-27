from modules.vlm_bridge.services.processor import VisionProcessor
from modules.vlm_bridge.services.vision_event_bus import EVENT_FACE_EMOTION, VisionEventBus


def test_face_emotion_event_requires_confidence_and_obeys_cooldown():
    processor = VisionProcessor.__new__(VisionProcessor)
    processor.event_bus = VisionEventBus()
    processor._face_emotion_event_min_confidence = 0.8
    processor._face_emotion_event_cooldown_s = 30.0
    processor._last_face_emotion_event = {}
    received = []
    processor.event_bus.subscribe(EVENT_FACE_EMOTION, lambda _kind, data: received.append(dict(data)))

    processor._publish_face_emotion_event("person-1", "Emir", "angry", 0.7)
    processor._publish_face_emotion_event("person-1", "Emir", "angry", 0.92)
    processor._publish_face_emotion_event("person-1", "Emir", "angry", 0.95)

    assert len(received) == 1
    assert received[0]["emotion"] == "angry"
    assert received[0]["confidence"] == 0.92


def test_neutral_face_emotion_does_not_publish():
    processor = VisionProcessor.__new__(VisionProcessor)
    processor.event_bus = VisionEventBus()
    processor._face_emotion_event_min_confidence = 0.5
    processor._face_emotion_event_cooldown_s = 0.0
    processor._last_face_emotion_event = {}
    received = []
    processor.event_bus.subscribe(EVENT_FACE_EMOTION, lambda *_args: received.append(True))

    processor._publish_face_emotion_event("person-1", "Emir", "neutral", 0.99)

    assert received == []
