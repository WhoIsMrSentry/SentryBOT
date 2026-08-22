from __future__ import annotations

import time

from modules.visual_output.neopixel.services.companion_leds import CompanionLedController, _interpolate_gradient


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
    assert all(driver.buf[i] == (0, 0, 0) for i in range(7, 23))


def test_wake_spin_can_retrigger():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg())
    ctrl.set_mode("wake_spin")
    first_started = ctrl._wake_spin_started
    ctrl.set_mode("wake_spin")
    assert ctrl.mode == "wake_spin"
    assert ctrl._wake_spin_started >= first_started


def test_wake_spin_blocks_external_mode_until_done():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg(wake_spin={"duration_ms": 5000, "wait_ms": 1}))
    ctrl.set_mode("wake_spin")
    ctrl.set_mode("thinking")
    assert ctrl.mode == "wake_spin"
    assert ctrl.status()["pending_mode"] == "thinking"


def test_wake_spin_defers_other_modes_until_animation_finishes():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(wake_spin={"duration_ms": 5000, "wait_ms": 1}),
    )
    ctrl.set_mode("wake_spin")
    ctrl.set_mode("thinking")
    assert ctrl.mode == "wake_spin"
    assert ctrl.status()["pending_mode"] == "thinking"
    ctrl._stop.set()
    if ctrl._thread:
        ctrl._thread.join(timeout=0.2)
    ctrl._wake_spin_started -= 10.0
    assert ctrl._render_wake_spin_frame() is True
    ctrl._complete_wake_spin()
    assert ctrl.mode == "thinking"


def test_companion_renderer_survives_off_then_restarts():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(
            tick_ms=5,
            wake_spin={"duration_ms": 100, "wait_ms": 5},
            colors={"wake_spin": "#FFD700"},
        ),
    )
    ctrl.set_mode("eye")
    time.sleep(0.03)
    ctrl.set_mode("off")
    shows_after_off = driver.shows
    ctrl.set_mode("wake_spin")
    time.sleep(0.03)
    ctrl._stop.set()
    assert driver.shows > shows_after_off
    assert any(driver.buf[i] != (0, 0, 0) for i in range(7))


def test_unknown_companion_mode_is_rejected():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg())
    assert ctrl.set_mode("random_mode") is False
    assert ctrl.mode == "off"


def test_face_frame_updates_eye_and_mirrors_right_brow():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(
            layout={
                "jewel_start": 0,
                "jewel_count": 7,
                "jewel_center_index": 0,
                "sticks": [
                    {"name": "left_brow", "start": 7, "count": 8, "channel": 0, "reverse": False},
                    {"name": "right_brow", "start": 15, "count": 8, "channel": 1, "reverse": True},
                ],
            },
            face={
                "pose_profiles": {
                    "neutral": {"intensity": 0.65, "slope": 0.0, "arch": 0.0},
                    "curious": {"intensity": 0.75, "slope": 0.30, "arch": 0.0},
                }
            },
        ),
    )
    assert ctrl.apply_face_frame(
        {
            "semantic": "curious_scan",
            "revision": "face-test-1",
            "eye": {"color": [20, 120, 220], "brightness": 1.0},
            "left_brow": {"pose": "curious", "intensity": 1.0},
            "right_brow": {"pose": "curious", "intensity": 1.0},
        },
        duration_ms=500,
    )
    ctrl._render_face_frame()
    assert ctrl.mode == "face"
    assert driver.shows >= 1
    assert all(driver.buf[idx] != (0, 0, 0) for idx in range(0, 7))
    assert driver.buf[7] == driver.buf[22]
    assert driver.buf[14] == driver.buf[15]
    assert driver.buf[7] != driver.buf[14]
    ctrl.stop()

def test_face_frame_expires_back_to_eye_mode():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(driver, _layout_cfg())
    assert ctrl.apply_face_frame({"semantic": "quiet_observation"}, duration_ms=100)
    ctrl._face_frame_expires_at = time.monotonic() - 0.01
    ctrl._render_face_frame()
    assert ctrl.mode == "eye"
    assert driver.shows >= 1
    ctrl.stop()


def test_companion_semantic_catalog_produces_named_face_frame():
    driver = _FakeDriver(23)
    ctrl = CompanionLedController(
        driver,
        _layout_cfg(
            face={
                "pose_profiles": {"neutral": {"intensity": 0.6, "slope": 0.0, "arch": 0.0}},
                "semantics": {
                    "quiet_observation": {
                        "description": "Quiet observation",
                        "animation": "EYE_EYEBROW",
                        "duration_ms": 300,
                        "frame": {
                            "eye": {"color": "#3366CC", "brightness": 0.8},
                            "left_brow": {"pose": "neutral"},
                            "right_brow": {"pose": "neutral"},
                        },
                    }
                },
            },
        ),
    )
    assert "quiet_observation" in ctrl.semantic_catalog()
    assert ctrl.apply_semantic("quiet_observation", revision="semantic-test")
    ctrl._render_face_frame()
    assert ctrl.mode == "face"
    assert all(driver.buf[idx] != (0, 0, 0) for idx in range(0, 23))
    assert ctrl.apply_semantic("not-a-real-semantic") is False
    ctrl.stop()
