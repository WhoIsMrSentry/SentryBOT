from modules.cognitive_memory.services.world_memory import WorldMemory
from modules.cognitive_memory.services.world_memory_autowriter import WorldMemoryAutoWriter


def test_vision_new_object_builds_object_memory_payload():
    writer = WorldMemoryAutoWriter()
    payloads = writer.from_vision({"new_object": True, "objects": ["red cube"], "summary": "new object on desk", "confidence": 0.8})
    assert payloads
    assert payloads[0]["kind"] == "objects"
    assert payloads[0]["name"] == "red cube"
    assert payloads[0]["source"] == "vision"


def test_vision_hazard_builds_event_payload():
    writer = WorldMemoryAutoWriter()
    payloads = writer.from_vision({"hazards": ["obstacle close"], "summary": "possible obstacle", "confidence": 0.9})
    assert any(p["kind"] == "events" and p["name"] == "hazard" for p in payloads)


def test_audio_wakeword_builds_owner_and_event_payloads():
    writer = WorldMemoryAutoWriter()
    payloads = writer.from_audio({"event_type": "wakeword", "wakeword": True, "owner_present": True, "confidence": 0.9})
    kinds_names = {(p["kind"], p["name"]) for p in payloads}
    assert ("people", "owner") in kinds_names
    assert ("events", "wakeword") in kinds_names


def test_audio_loud_builds_safety_event():
    writer = WorldMemoryAutoWriter()
    payloads = writer.from_audio({"event_type": "loud", "loud": True, "confidence": 0.8})
    assert any(p["kind"] == "events" and p["name"] == "loud noise" and "safety" in p.get("tags", []) for p in payloads)


def test_autowriter_payloads_merge_in_world_memory():
    mem = WorldMemory()
    writer = WorldMemoryAutoWriter()
    for payload in writer.from_audio({"event_type": "wakeword", "wakeword": True, "owner_present": True, "confidence": 0.9}):
        mem.observe(payload, source=payload.get("source", "audio"), now=1.0)
    for payload in writer.from_audio({"event_type": "wakeword", "wakeword": True, "owner_present": True, "confidence": 0.9}):
        mem.observe(payload, source=payload.get("source", "audio"), now=2.0)
    people = mem.recent(kind="people", limit=5)["items"]
    owner = next(item for item in people if item["name"] == "owner")
    assert owner["count"] == 2
