from __future__ import annotations

from typing import Any, Dict, List

from modules.animate.xAnimateService import xAnimateService


class FakeSerial:
    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def set_pose(self, pose: list[int], duration_ms: int | None = None):
        self.sent.append({"cmd": "set_pose", "pose": pose, "duration_ms": duration_ms})


class FailingSerial(FakeSerial):
    def set_pose(self, pose: list[int], duration_ms: int | None = None):
        raise RuntimeError("serial unavailable")


def test_run_sit(tmp_path):
    svc = xAnimateService(serial=FakeSerial())
    # ensure sit.yml exists in default animations dir; list should contain 'sit'
    assert 'sit' in svc.list()
    svc.run('sit', speed=1.0, loop=False)
    # at least one set_pose should be sent
    assert len(svc.serial.sent) >= 1  # type: ignore[attr-defined]


def test_legacy_pose_is_normalized_to_4_servos():
    svc = xAnimateService(serial=FakeSerial())
    out = svc._normalize_pose([90, 110, 60, 90, 110, 60, 88, 120])
    assert out == [120, 88, 90, 90]


def test_run_does_not_raise_when_serial_unavailable():
    svc = xAnimateService(serial=FailingSerial())
    svc.run('blink', speed=1.0, loop=False)
