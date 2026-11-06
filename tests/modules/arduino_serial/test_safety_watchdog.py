import time
import pytest

from modules.arduino_serial.services.safety_watchdog import HardwareSafetyWatchdog


def test_watchdog_lifecycle():
    tripped_reasons = []

    def on_estop(reason: str):
        tripped_reasons.append(reason)

    wd = HardwareSafetyWatchdog(
        timeout_s=0.3,
        check_interval_s=0.05,
        on_estop_callback=on_estop,
    )
    assert wd.status()["active"] is False

    wd.start()
    assert wd.status()["active"] is True
    assert wd.status()["tripped"] is False

    # Feed periodically
    for _ in range(4):
        time.sleep(0.08)
        wd.feed("test_feed")

    # Should not be tripped because we fed it
    assert wd.status()["tripped"] is False
    assert len(tripped_reasons) == 0

    # Now let it expire
    time.sleep(0.4)
    status = wd.status()
    assert status["tripped"] is True
    assert len(tripped_reasons) == 1
    assert "timeout" in tripped_reasons[0].lower()

    # Test re-arm
    wd.reset_trip()
    assert wd.status()["tripped"] is False

    wd.stop()
    assert wd.status()["active"] is False

