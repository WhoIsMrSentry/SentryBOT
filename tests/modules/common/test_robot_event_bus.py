from __future__ import annotations

from modules.common.event_bus import (
    RobotEvent,
    RobotEventBus,
    get_robot_event_bus,
    reset_robot_event_bus,
)


def test_exact_and_wildcard_subscriptions() -> None:
    bus = RobotEventBus(maxlen=16)
    exact_received: list[RobotEvent] = []
    prefix_received: list[RobotEvent] = []
    all_received: list[RobotEvent] = []

    sub_exact = bus.subscribe("vision.person_detected", exact_received.append)
    sub_prefix = bus.subscribe("vision.*", prefix_received.append)
    sub_all = bus.subscribe("*", all_received.append)

    ev1 = bus.publish(
        "vision.person_detected",
        {"person_id": "alice", "confidence": 0.94},
        source="vlm_bridge",
        priority=80,
    )
    ev2 = bus.publish(
        "vision.motion",
        {"zone": "center"},
        source="camera",
        priority=60,
    )
    ev3 = bus.publish(
        "speech.utterance",
        {"text": "merhaba"},
        source="speech",
        priority=70,
    )

    assert len(exact_received) == 1
    assert exact_received[0] == ev1
    assert exact_received[0].payload["person_id"] == "alice"
    assert exact_received[0].source == "vlm_bridge"
    assert exact_received[0].priority == 80

    assert [e.topic for e in prefix_received] == ["vision.person_detected", "vision.motion"]
    assert [e.topic for e in all_received] == [
        "vision.person_detected",
        "vision.motion",
        "speech.utterance",
    ]
    assert ev2.timestamp <= ev3.timestamp

    assert bus.unsubscribe(sub_exact) is True
    assert bus.unsubscribe(sub_exact) is False
    bus.publish("vision.person_detected", {"person_id": "bob"})
    assert len(exact_received) == 1
    assert len(prefix_received) == 3
    assert bus.unsubscribe(sub_prefix) is True
    assert bus.unsubscribe(sub_all) is True


def test_bounded_history_and_recent_filtering() -> None:
    bus = RobotEventBus(maxlen=5)
    for idx in range(7):
        topic = f"sensor.cliff.{idx}" if idx % 2 == 0 else f"audio.doa.{idx}"
        bus.publish(topic, {"idx": idx}, source="arduino", priority=50 + idx)

    assert len(bus) == 5
    all_recent = bus.recent(limit=10)
    assert len(all_recent) == 5
    assert [item["payload"]["idx"] for item in all_recent] == [2, 3, 4, 5, 6]

    sensor_recent = bus.recent(topic_prefix="sensor.cliff", limit=2)
    assert len(sensor_recent) == 2
    assert [item["topic"] for item in sensor_recent] == ["sensor.cliff.4", "sensor.cliff.6"]
    assert bus.recent_events(topic_prefix="audio.", limit=5) == bus.recent(
        topic_prefix="audio.", limit=5
    )


def test_singleton_and_subscriber_error_isolation() -> None:
    reset_robot_event_bus()
    bus = get_robot_event_bus()
    seen: list[str] = []

    def _bad_listener(_event: RobotEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe("system.*", _bad_listener)
    bus.subscribe("system.*", lambda ev: seen.append(ev.topic))

    bus.publish("system.ready", {"ok": True})
    assert seen == ["system.ready"]
    assert get_robot_event_bus() is bus

    reset_robot_event_bus()
    assert get_robot_event_bus() is not bus
    assert len(get_robot_event_bus()) == 0
