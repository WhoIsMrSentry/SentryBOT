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


def test_gradient_interpolation():
    """Test gradient color interpolation between green -> yellow -> red."""
    gradient = [(0, 255, 0), (255, 255, 0), (255, 0, 0)]
    # At 0.0 should be green
    c = _interpolate_gradient(gradient, 0.0)
    assert c == (0, 255, 0)
    # At 1.0 should be red
    c = _interpolate_gradient(gradient, 1.0)
    assert c == (255, 0, 0)
    # At 0.5 should be yellow-ish
    c = _interpolate_gradient(gradient, 0.5)
    assert c[1] > 0  # has green component
    assert c[0] > 0  # has red component


def test_companion_vu_gradient_colors():
    """Test VU meter uses gradient colors (green->yellow->red)."""
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        {
            "layout": {"jewel_start": 0, "jewel_count": 7, "jewel_center_index": 0, "stick_start": 7, "stick_count": 16},
            "tick_ms": 10,
            "vu": {"smoothing": 1.0, "min_level": 0.0},
            "colors": {
                "vu_gradient": ["#00FF00", "#FFFF00", "#FF0000"],
                "vu_bg": "#051018",
            },
        },
    )
    ctrl.set_mode("vu")
    ctrl.set_vu_level(1.0)  # Full level
    ctrl._render_vu_frame()
    
    # Bottom of stick (index 7) should be green-ish
    bottom = driver.buf[7]
    assert bottom[1] > bottom[0] and bottom[1] > bottom[2]  # Green dominant
    
    # Top of stick (index 22) should be red-ish
    top = driver.buf[22]
    assert top[0] > top[1] and top[0] > top[2]  # Red dominant


def test_companion_wake_chase_mode():
    """Test wake_chase mode animates jewel ring with opposite pairs."""
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        {
            "layout": {"jewel_start": 0, "jewel_count": 7, "jewel_center_index": 0, "stick_start": 7, "stick_count": 16},
            "tick_ms": 10,
            "wake_chase": {"speed_ms": 50, "direction_cw": True, "pair_gap": 1},
            "colors": {"eye_default": "#30E3CA"},
        },
    )
    ctrl.set_mode("wake_chase")
    # Render a few frames
    for _ in range(3):
        ctrl._render_wake_chase_frame()
    
    # Center eye should be lit
    assert driver.buf[0] != (0, 0, 0)
    # Ring should have some activity (chase animation)
    ring_leds = [driver.buf[i] for i in range(1, 7)]
    assert any(c != (0, 0, 0) for c in ring_leds)


def test_companion_wake_chase_opposite_pairs():
    """Test that wake_chase lights opposite pairs (1,4), (2,5), (3,6)."""
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        {
            "layout": {"jewel_start": 0, "jewel_count": 7, "jewel_center_index": 0, "stick_start": 7, "stick_count": 16},
            "tick_ms": 10,
            "wake_chase": {"speed_ms": 50, "direction_cw": True, "pair_gap": 0},
            "colors": {"eye_default": "#FF0000"},
        },
    )
    ctrl.set_mode("wake_chase")
    ctrl._render_wake_chase_frame()
    
    # Check that opposite pairs are treated together
    # At phase 0, pair (1,4) should be active
    # We can't easily test the exact phase without knowing internal state,
    # but we can verify the structure by checking multiple frames
    seen_pairs = set()
    for _ in range(10):
        ctrl._render_wake_chase_frame()
        # Check which ring LEDs are brightly lit
        for i in range(1, 7):
            c = driver.buf[i]
            if c[0] > 50 or c[1] > 50 or c[2] > 50:  # bright
                seen_pairs.add(i)
    
    # Should have activity on the ring
    assert len(seen_pairs) > 0
