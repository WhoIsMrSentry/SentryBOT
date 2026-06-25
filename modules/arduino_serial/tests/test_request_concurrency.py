"""Regression test for concurrent request() calls sharing one Arduino link.

Before the ``_request_lock`` fix, two threads calling ``request()`` at the
same time both consumed from the same ``_rx_queue`` with no correlation
beyond a generic ``ok``/``err`` check. A slow reply to one caller's command
could be delivered to a *different* caller waiting on a different command
(e.g. an ``estop`` caller receiving a ``set_servo`` ACK). This test proves
concurrent callers always receive the reply that matches their own command.
"""

from __future__ import annotations

import json
import threading
import time

from modules.arduino_serial.tests.fake_transport_sim import FakeTransportSim
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


class _SlowFirstTransport(FakeTransportSim):
    """Replies to "slow_cmd" only after a delay, "fast_cmd" immediately.

    This reproduces the real-world ordering where a second, quicker command
    can get a response before an earlier, slower one -- the exact situation
    where an un-serialized request() could hand a caller the wrong reply.
    """

    def write(self, data: bytes) -> int:
        text = data.decode("utf-8", errors="ignore").strip()
        obj = json.loads(text.splitlines()[0]) if text else {}
        cmd = obj.get("cmd")

        if cmd == "slow_cmd":

            def _delayed_reply():
                time.sleep(0.15)
                self.inject_msg({"ok": True, "which": "slow"})

            threading.Thread(target=_delayed_reply, daemon=True).start()
            with self._lock:
                self._buf += data
            return len(data)

        if cmd == "fast_cmd":
            self.inject_msg({"ok": True, "which": "fast"})
            with self._lock:
                self._buf += data
            return len(data)

        return super().write(data)


def test_concurrent_requests_do_not_cross_talk():
    dt = _SlowFirstTransport()
    svc = xArduinoSerialService(
        config_overrides={"transport": "serial"}, transport_factory=lambda *a, **k: dt
    )
    svc.start()
    results: dict[str, dict] = {}

    def _call(name: str, cmd: str):
        results[name] = svc.request({"cmd": cmd}, timeout=2.0)

    try:
        t_slow = threading.Thread(target=_call, args=("slow", "slow_cmd"))
        t_fast = threading.Thread(target=_call, args=("fast", "fast_cmd"))

        t_slow.start()
        time.sleep(0.03)  # ensure slow_cmd is sent and awaiting its reply first
        t_fast.start()

        t_slow.join(timeout=3.0)
        t_fast.join(timeout=3.0)

        assert results["slow"].get("which") == "slow", (
            "slow_cmd caller received a mismatched reply: %r" % (results.get("slow"),)
        )
        assert results["fast"].get("which") == "fast", (
            "fast_cmd caller received a mismatched reply: %r" % (results.get("fast"),)
        )
    finally:
        svc.stop()
