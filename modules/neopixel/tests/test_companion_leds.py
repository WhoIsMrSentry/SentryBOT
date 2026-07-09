from __future__ import annotations

from modules.neopixel.services.companion_leds import CompanionLedController


class _FakeDriver:
    def __init__(self, n: int = 23):
        self.num_leds = n
        self.buf = [(0, 0, 0)] * n
        self.shows = 0

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        self.buf[idx] = (r, g, b)

    def show(self) -> None:
        self.shows += 1


def test_companion_vu_fills_strip_not_jewel_center():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        {
            "layout": {"jewel_start": 0, "jewel_count": 7, "jewel_center_index": 0, "stick_start": 7, "stick_count": 16},
            "tick_ms": 10,
        },
    )
    ctrl.set_mode("vu")
    ctrl.set_vu_level(0.5)
    ctrl._render_vu_frame()
    assert driver.buf[0] != (0, 0, 0)  # eye
    assert any(driver.buf[i] != (0, 0, 0) for i in range(7, 15))


def test_companion_thinking_alternates_ring():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        {"layout": {"jewel_start": 0, "jewel_count": 7, "jewel_center_index": 0, "stick_start": 7, "stick_count": 16}, "tick_ms": 1},
    )
    ctrl.set_mode("thinking")
    ctrl._render_thinking_frame()
    ring = driver.buf[1:7]
    assert any(c != (0, 0, 0) for c in ring)
    assert driver.buf[0] != (0, 0, 0)
