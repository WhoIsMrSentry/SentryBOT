from __future__ import annotations
from pathlib import Path

import yaml

from modules.visual_output.neopixel.services.driver import NeoDriverConfig
from modules.visual_output.neopixel.services.runner import NeoRunner


class _FakeDriver:
    def __init__(self, n: int):
        self.num_leds = n
        self.buf = [(0, 0, 0)] * n
        self.shows = 0

    def clear(self):
        self.buf = [(0, 0, 0)] * self.num_leds

    def set(self, idx: int, r: int, g: int, b: int):
        self.buf[idx] = (r, g, b)

    def show(self):
        self.shows += 1

    def fill(self, r: int, g: int, b: int):
        self.buf = [(r, g, b)] * self.num_leds

    def animate(self, name: str, r: int = 255, g: int = 255, b: int = 255, iterations: int = 0, speed_ms: int = 50):
        return False


def test_fill_segment_applies_only_target_range():
    runner = NeoRunner(
        NeoDriverConfig(num_leds=10),
        segments=[{"name": "jewel", "start": 0, "count": 3}, {"name": "stick", "start": 3, "count": 7}],
    )
    runner.driver = _FakeDriver(10)

    ok = runner.fill_segment("jewel", 9, 8, 7)
    assert ok is True
    assert runner.driver.buf[:3] == [(9, 8, 7), (9, 8, 7), (9, 8, 7)]
    assert runner.driver.buf[3:] == [(0, 0, 0)] * 7


def test_animate_unknown_effect_on_segment_falls_back_to_segment_fill():
    runner = NeoRunner(NeoDriverConfig(num_leds=6), segments=[{"name": "jewel", "start": 0, "count": 2}])
    runner.driver = _FakeDriver(6)
    runner.animate("NO_SUCH_EFFECT", color=(10, 20, 30), segment="jewel")
    runner._wait_for_animations()
    assert runner.driver.buf[0] == (10, 20, 30)
    assert runner.driver.buf[1] == (10, 20, 30)
    assert runner.driver.buf[2:] == [(0, 0, 0)] * 4


def test_animate_known_effect_runs_scoped_to_segment():
    # A real animation must run on the segment range only, leaving the rest dark.
    runner = NeoRunner(NeoDriverConfig(num_leds=6), segments=[{"name": "jewel", "start": 0, "count": 2}])
    runner.driver = _FakeDriver(6)
    runner.animate("PULSE", color=(200, 100, 50), segment="jewel")
    runner._wait_for_animations()
    # Segment LEDs were driven by the effect (non-zero), neighbours untouched.
    assert runner.driver.buf[0] != (0, 0, 0)
    assert runner.driver.buf[1] != (0, 0, 0)
    assert runner.driver.buf[2:] == [(0, 0, 0)] * 4
    assert runner.driver.shows > 0


def test_apply_preset_sets_segment_colors():
    runner = NeoRunner(
        NeoDriverConfig(num_leds=8),
        segments=[{"name": "jewel", "start": 0, "count": 2}, {"name": "stick", "start": 2, "count": 6}],
        presets={"calm": {"jewel": {"color": [1, 2, 3]}, "stick": {"color": "#040506"}}},
    )
    runner.driver = _FakeDriver(8)
    ok = runner.apply_preset("calm")
    assert ok is True
    assert runner.driver.buf[0] == (1, 2, 3)
    assert runner.driver.buf[1] == (1, 2, 3)
    assert runner.driver.buf[2] == (4, 5, 6)


def test_apply_unknown_preset_returns_false():
    runner = NeoRunner(NeoDriverConfig(num_leds=4), segments=[], presets={})
    assert runner.apply_preset("missing") is False


def test_runtime_preset_crud():
    runner = NeoRunner(NeoDriverConfig(num_leds=4), segments=[], presets={})
    v0 = runner.preset_version()
    assert runner.set_preset("temp", {"jewel": {"color": [1, 2, 3]}}) is True
    assert runner.preset_version() == v0
    data = runner.get_preset("temp")
    assert isinstance(data, dict)
    assert "jewel" in data
    assert runner.delete_preset("temp") is True
    assert runner.get_preset("temp") is None


def test_preset_persistence_writes_yaml_and_increments_version(tmp_path: Path):
    cfg_path = tmp_path / "neo.yml"
    cfg_path.write_text(
        "server:\n"
        "  host: 0.0.0.0\n"
        "presets_meta:\n"
        "  version: 4\n"
        "presets: {}\n",
        encoding="utf-8",
    )
    runner = NeoRunner(
        NeoDriverConfig(num_leds=4),
        segments=[],
        presets={},
        preset_store_path=str(cfg_path),
        preset_version=4,
    )

    assert runner.set_preset("demo", {"jewel": {"color": [7, 8, 9]}}, persist=True) is True
    saved = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert saved["presets"]["demo"]["jewel"]["color"] == [7, 8, 9]
    assert saved["presets_meta"]["version"] == 5
    assert runner.preset_version() == 5
