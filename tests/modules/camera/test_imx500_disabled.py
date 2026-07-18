"""Smoke tests for the IMX500 runner + on-sensor event bus.

These tests intentionally exercise the *disabled* path so they can run on any
developer machine. They guard against regressions in the import-on-import-time
behaviour (the runner must stay inert when ``picamera2`` is missing) and verify
that the bus retains the latest snapshot.
"""

from __future__ import annotations

import time

import pytest

from modules.camera.services import imx500_runner as runner_mod
from modules.camera.services.imx500_runner import Imx500Config, Imx500Runner
from modules.camera.services.onsensor_bus import (
    OnSensorDetection,
    OnSensorEventBus,
    OnSensorSnapshot,
)


def test_imx500_disabled_when_config_off():
    cfg = Imx500Config(enabled=False)
    bus = OnSensorEventBus()
    runner = Imx500Runner(cfg, bus=bus)
    assert runner.available is False
    assert runner.start() is False


def test_imx500_disabled_when_library_missing(monkeypatch):
    monkeypatch.setattr(runner_mod, "IMX500_AVAILABLE", False)
    cfg = Imx500Config(enabled=True, model_path="/nonexistent.rpk")
    runner = Imx500Runner(cfg, bus=OnSensorEventBus())
    assert runner.available is False
    assert runner.start() is False


def test_bus_publish_and_history():
    bus = OnSensorEventBus(history_size=2)
    received = []
    bus.subscribe(lambda snap: received.append(snap))

    snap1 = OnSensorSnapshot(
        ts=time.time(),
        frame_id=1,
        detections=[
            OnSensorDetection(class_id=0, label="person", score=0.9, bbox_xyxy_norm=(0.1, 0.1, 0.4, 0.6)),
        ],
    )
    snap2 = OnSensorSnapshot(
        ts=time.time(),
        frame_id=2,
        detections=[],
    )
    bus.publish(snap1)
    bus.publish(snap2)

    latest = bus.latest()
    assert latest is snap2
    assert len(received) == 2
    assert [s.frame_id for s in received] == [1, 2]
    assert bus.stats()["published_count"] == 2
    history = bus.history()
    assert [s.frame_id for s in history] == [1, 2]


def test_bus_history_size_capped():
    bus = OnSensorEventBus(history_size=2)
    for i in range(5):
        bus.publish(OnSensorSnapshot(frame_id=i))
    history = bus.history()
    assert len(history) == 2
    assert history[-1].frame_id == 4


def test_runner_unpacks_dict_outputs(monkeypatch):
    """Even with the library missing, the unpack helper should be defensive."""

    cfg = Imx500Config(enabled=False)
    runner = Imx500Runner(cfg, bus=OnSensorEventBus())
    boxes, scores, classes = runner._unpack([
        {
            "boxes": [(0.1, 0.1, 0.2, 0.2), (0.3, 0.3, 0.5, 0.5)],
            "scores": [0.91, 0.42],
            "classes": [0, 1],
        }
    ])
    assert boxes == [(0.1, 0.1, 0.2, 0.2), (0.3, 0.3, 0.5, 0.5)]
    assert scores == [0.91, 0.42]
    assert classes == [0, 1]

    boxes2, scores2, classes2 = runner._unpack([
        [[(0.0, 0.0, 1.0, 1.0)]],
        [[0.77]],
        [[3]],
    ])
    assert classes2 == [3]
    assert scores2[0] == pytest.approx(0.77)
    assert boxes2 == [(0.0, 0.0, 1.0, 1.0)]
