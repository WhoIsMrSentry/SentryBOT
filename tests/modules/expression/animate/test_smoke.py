from __future__ import annotations

from typing import Any, Dict, List

from modules.expression.animate.xAnimateService import xAnimateService


class FakeSerial:
    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def set_pose(self, pose: list[int], duration_ms: int | None = None, source: str = "autonomy"):
        self.sent.append({"cmd": "set_pose", "pose": pose, "duration_ms": duration_ms})

    def set_servo(self, index: int, deg: float, source: str = "autonomy"):
        self.sent.append({"cmd": "set_servo", "index": index, "deg": deg})


class FailingSerial(FakeSerial):
    def set_pose(self, pose: list[int], duration_ms: int | None = None, source: str = "autonomy"):
        raise RuntimeError("serial unavailable")

    def set_servo(self, index: int, deg: float, source: str = "autonomy"):
        raise RuntimeError("serial unavailable")


def test_run_sit(tmp_path):
    svc = xAnimateService(serial=FakeSerial())
    assert "sit" in svc.list()
    svc.run("sit", speed=1.0, loop=False)
    assert len(svc.serial.sent) >= 1  # type: ignore[attr-defined]


def test_legacy_pose_holds_ears():
    svc = xAnimateService(serial=FakeSerial())
    out = svc._normalize_pose([90, 110, 60, 90, 110, 60, 88, 120])
    assert out == [120, 88, None, None]


def test_two_value_pose_holds_ears():
    svc = xAnimateService(serial=FakeSerial())
    out = svc._normalize_pose([82, 75])
    assert out == [82, 75, None, None]


def test_run_head_only_uses_set_servo():
    serial = FakeSerial()
    svc = xAnimateService(serial=serial)
    svc.run("blink", speed=1.0, loop=False)
    assert any(item["cmd"] == "set_servo" for item in serial.sent)
    assert all(item["cmd"] != "set_pose" for item in serial.sent)


def test_run_does_not_raise_when_serial_unavailable():
    svc = xAnimateService(serial=FailingSerial())
    svc.run("blink", speed=1.0, loop=False)
