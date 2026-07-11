from __future__ import annotations

from modules.neopixel.services.companion_leds import CompanionLedController, _interpolate_gradient


class _FakeDriver:
    def __init__(self, n: int = 23):
        self.num_leds = n
        self.buf = [(0, 0, 0)] * n
        self.shows = 0

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        self.buf[idx] = (r, g, b)

    def show(self) -> None:
        self.shows += 1


def _layout_cfg(**extra):
    base = {
        "layout": {
            "jewel_start": 0,
            "jewel_count": 7,
            "jewel_center_index": 0,
            "sticks": [
                {"start": 7, "count": 8, "channel": 0},
                {"start": 15, "count": 8, "channel": 1},
            ],
        },
        "tick_ms": 10,
    }
    base.update(extra)
    return base


def test_companion_vu_fills_strips_not_jewel_center():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg(vu={"attack": 1.0, "decay": 1.0, "min_level": 0.0}))
    ctrl.set_mode("listen_vu")
    ctrl.set_vu_level(0.5, right=0.0)
    ctrl._render_vu_frame()
    assert driver.buf[0] != (0, 0, 0)
    assert any(driver.buf[i] != (5, 16, 24) for i in range(7, 15))
    assert all(driver.buf[i] == (5, 16, 24) for i in range(15, 23))


def test_companion_stereo_vu_independent_channels():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(vu={"attack": 1.0, "decay": 1.0, "min_level": 0.0}),
    )
    ctrl.set_mode("listen_vu")
    ctrl.set_vu_level(0.9, right=0.1)
    ctrl._render_vu_frame()
    left_lit = sum(1 for i in range(7, 15) if driver.buf[i] != (5, 16, 24))
    right_lit = sum(1 for i in range(15, 23) if driver.buf[i] != (5, 16, 24))
    assert left_lit > right_lit


def test_companion_thinking_alternates_ring():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg(tick_ms=1))
    ctrl.set_mode("thinking")
    ctrl._render_thinking_frame()
    ring = driver.buf[1:7]
    assert any(c != (0, 0, 0) for c in ring)
    assert driver.buf[0] != (0, 0, 0)


def test_gradient_interpolation():
    gradient = [(0, 255, 0), (255, 255, 0), (255, 0, 0)]
    c = _interpolate_gradient(gradient, 0.0)
    assert c == (0, 255, 0)
    c = _interpolate_gradient(gradient, 1.0)
    assert c == (255, 0, 0)
    c = _interpolate_gradient(gradient, 0.5)
    assert c[1] > 0
    assert c[0] > 0


def test_companion_vu_gradient_colors():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(
            vu={"attack": 1.0, "decay": 1.0, "min_level": 0.0},
            colors={
                "vu_gradient": ["#00FF00", "#FFFF00", "#FF0000"],
                "vu_bg": "#051018",
            },
        ),
    )
    ctrl.set_mode("vu")
    ctrl.set_vu_level(1.0)
    ctrl._render_vu_frame()
    bottom = driver.buf[7]
    assert bottom[1] > bottom[0] and bottom[1] > bottom[2]
    top = driver.buf[14]
    assert top[0] > top[1] and top[0] > top[2]


def test_companion_wake_spin_jewel_only_golden():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(
            wake_spin={"duration_ms": 5000, "wait_ms": 1},
            colors={"wake_spin": "#FFD700"},
        ),
    )
    ctrl.set_mode("wake_spin")
    ctrl._render_wake_spin_frame()
    assert any(driver.buf[i] != (0, 0, 0) for i in range(0, 7))
    assert all(driver.buf[i] == (5, 16, 24) for i in range(7, 23))


def test_vu_level_from_off_enters_listen_vu():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg(vu={"attack": 1.0, "decay": 1.0, "min_level": 0.02}))
    assert ctrl.mode == "off"
    ctrl.set_vu_level(0.5, right=0.3)
    assert ctrl.mode == "listen_vu"


def test_wake_spin_can_retrigger():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg())
    ctrl.set_mode("wake_spin")
    first_started = ctrl._wake_spin_started
    ctrl.set_mode("wake_spin")
    assert ctrl.mode == "wake_spin"
    assert ctrl._wake_spin_started >= first_started


def test_wake_spin_blocks_external_listen_vu_until_done():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg())
    ctrl.set_mode("wake_spin")
    ctrl.set_mode("listen_vu")
    assert ctrl.mode == "wake_spin"
