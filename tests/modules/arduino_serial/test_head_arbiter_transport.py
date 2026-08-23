from __future__ import annotations

from modules.arduino_serial.head_arbiter_integration import HeadArbiterTransportWrapper
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class _FakeArbiter:
    def __init__(self, allow: bool = True):
        self.allow = allow
        self.calls: list[dict] = []

    def move(self, pan=None, tilt=None, source="autonomy", priority=30):
        self.calls.append({"pan": pan, "tilt": tilt, "source": source, "priority": priority})
        if self.allow:
            return {"ok": True, "pan": pan, "tilt": tilt}
        return {"ok": False, "reason": "resource_locked"}


def _wrapper(arbiter) -> HeadArbiterTransportWrapper:
    return HeadArbiterTransportWrapper(head_arbiter=arbiter, enable=True)


def test_set_servo_pan_tilt_is_gated_by_arbiter():
    arb = _FakeArbiter()
    w = _wrapper(arb)
    cmd = {"cmd": "set_servo", "index": 0, "deg": 100.0}
    assert w.is_head_command(cmd) is True
    wrapped = w.wrap_command(cmd, source="animate")
    assert wrapped["deg"] == 100.0
    # First single-axis call fills the other axis from last-known state.
    assert arb.calls[-1]["pan"] == 100.0
    assert arb.calls[-1]["priority"] == 90


def test_set_servo_denial_raises_instead_of_bypassing():
    w = _wrapper(_FakeArbiter(allow=False))
    try:
        w.wrap_command({"cmd": "set_servo", "index": 1, "deg": 80.0}, source="autonomy")
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


def test_set_servo_ear_index_bypasses_arbiter():
    arb = _FakeArbiter()
    w = _wrapper(arb)
    cmd = {"cmd": "set_servo", "index": 2, "deg": 45.0}
    assert w.is_head_command(cmd) is False
    assert w.wrap_command(cmd, source="animate") == cmd
    assert arb.calls == []


def test_track_updates_last_known_axes_for_single_axis_servos():
    arb = _FakeArbiter()
    w = _wrapper(arb)
    w.wrap_command({"cmd": "track", "pan": 120.0, "tilt": 70.0}, source="vlm_bridge")
    w.wrap_command({"cmd": "set_servo", "index": 1, "deg": 60.0}, source="animate")
    # Tilt servo moved to 60 while pan stays at last tracked value.
    assert arb.calls[-1]["tilt"] == 60.0
    assert arb.calls[-1]["pan"] == 120.0


def _bare_service() -> xArduinoSerialService:
    svc = xArduinoSerialService.__new__(xArduinoSerialService)
    svc._logger = __import__("logging").getLogger("test")
    svc._head_arbiter_wrapper = None
    return svc


def test_service_set_head_arbiter_rebuilds_wrapper():
    svc = _bare_service()
    first = _FakeArbiter()
    second = _FakeArbiter()

    svc.set_head_arbiter(first)
    wrapper_first = svc._head_arbiter_wrapper
    assert wrapper_first is not None and wrapper_first.head_arbiter is first

    svc.set_head_arbiter(second)
    assert svc._head_arbiter_wrapper is not wrapper_first
    assert svc._head_arbiter_wrapper.head_arbiter is second
