"""Unit tests for PiSsd1306Driver (non-hardware paths)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from modules.oled_faces.services.pi_ssd1306_driver import PiSsd1306Driver


def _make_driver(assets_dir: str | None = None, enabled: bool = False) -> PiSsd1306Driver:
    cfg: dict = {"enabled": enabled}
    if assets_dir is not None:
        cfg["assets_dir"] = assets_dir
    return PiSsd1306Driver(cfg)


# ---------------------------------------------------------------------------
# Buffer / pixel manipulation (no I2C required)
# ---------------------------------------------------------------------------

class TestBufferOps:
    def test_clear_zeroes_buffer(self):
        d = _make_driver()
        d._buffer[0] = 0xFF
        d.clear()
        assert all(b == 0 for b in d._buffer)

    def test_set_pixel_on(self):
        d = _make_driver()
        d.clear()
        d.set_pixel(0, 0, 1)
        # pixel (0,0) is bit 0 of byte index 0
        assert d._buffer[0] & 0x01

    def test_set_pixel_off(self):
        d = _make_driver()
        d.clear()
        d.set_pixel(0, 0, 1)
        d.set_pixel(0, 0, 0)
        assert not (d._buffer[0] & 0x01)

    def test_set_pixel_out_of_bounds_is_noop(self):
        d = _make_driver()
        d.clear()
        d.set_pixel(-1, 0)
        d.set_pixel(0, -1)
        d.set_pixel(d.width, 0)
        d.set_pixel(0, d.height)
        assert all(b == 0 for b in d._buffer)

    def test_buffer_size(self):
        d = _make_driver()
        assert len(d._buffer) == (d.width * d.height) // 8


# ---------------------------------------------------------------------------
# show_test_pattern pixel calculation (enabled=False means _ok is False)
# ---------------------------------------------------------------------------

class TestShowTestPattern:
    def test_show_test_pattern_requires_ok(self):
        d = _make_driver()  # enabled=False, _ok=False
        assert d.show_test_pattern() is False


# ---------------------------------------------------------------------------
# _load_bitmap padding / truncation logic
# ---------------------------------------------------------------------------

class TestLoadBitmap:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.bitmaps_dir = Path(self.tmp) / "bitmaps"
        self.bitmaps_dir.mkdir()
        self.animations_dir = Path(self.tmp) / "animations"
        self.animations_dir.mkdir()
        self.driver = _make_driver(assets_dir=self.tmp)

    def _write_bitmap(self, name: str, data: bytes):
        (self.bitmaps_dir / f"{name}.bin").write_bytes(data)

    def test_exact_size(self):
        size = len(self.driver._buffer)
        data = bytes([i % 256 for i in range(size)])
        self._write_bitmap("exact", data)
        result = self.driver._load_bitmap("exact")
        assert result is not None
        assert len(result) == size
        assert result == data

    def test_short_bitmap_is_padded(self):
        size = len(self.driver._buffer)
        self._write_bitmap("short", b"\xFF" * 10)
        result = self.driver._load_bitmap("short")
        assert result is not None
        assert len(result) == size
        assert result[:10] == b"\xFF" * 10
        assert result[10:] == b"\x00" * (size - 10)

    def test_long_bitmap_is_truncated(self):
        size = len(self.driver._buffer)
        self._write_bitmap("long", b"\xAB" * (size + 50))
        result = self.driver._load_bitmap("long")
        assert result is not None
        assert len(result) == size

    def test_missing_bitmap_returns_none(self):
        assert self.driver._load_bitmap("nonexistent") is None

    def test_bitmap_is_cached(self):
        size = len(self.driver._buffer)
        self._write_bitmap("cached", b"\x11" * size)
        result1 = self.driver._load_bitmap("cached")
        # Overwrite the file – cached result should still be returned
        (self.bitmaps_dir / "cached.bin").write_bytes(b"\x22" * size)
        result2 = self.driver._load_bitmap("cached")
        assert result1 == result2


# ---------------------------------------------------------------------------
# _load_animation JSON parsing
# ---------------------------------------------------------------------------

class TestLoadAnimation:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        (Path(self.tmp) / "bitmaps").mkdir()
        self.animations_dir = Path(self.tmp) / "animations"
        self.animations_dir.mkdir()
        self.driver = _make_driver(assets_dir=self.tmp)

    def _write_anim(self, name: str, data: dict):
        (self.animations_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_basic_animation_parsed(self):
        self._write_anim("test_anim", {"frames": ["a", "b", "c"], "delay_ms": 200})
        frames, delay = self.driver._load_animation("test_anim")
        assert frames == ["a", "b", "c"]
        assert abs(delay - 0.2) < 1e-6

    def test_delay_clamped_to_minimum(self):
        self._write_anim("fast", {"frames": ["x"], "delay_ms": 1})
        _, delay = self.driver._load_animation("fast")
        assert delay >= 0.05

    def test_missing_animation_returns_empty(self):
        frames, _ = self.driver._load_animation("missing")
        assert frames == []

    def test_empty_frame_names_filtered(self):
        self._write_anim("empties", {"frames": ["a", "", "  ", "b"], "delay_ms": 100})
        frames, _ = self.driver._load_animation("empties")
        assert frames == ["a", "b"]

    def test_animation_is_cached(self):
        self._write_anim("cached_anim", {"frames": ["x", "y"], "delay_ms": 150})
        result1 = self.driver._load_animation("cached_anim")
        # Overwrite file; cached result should still be returned
        (self.animations_dir / "cached_anim.json").write_text(
            json.dumps({"frames": ["z"], "delay_ms": 50}), encoding="utf-8"
        )
        result2 = self.driver._load_animation("cached_anim")
        assert result1 == result2

    def test_malformed_json_returns_empty(self):
        (self.animations_dir / "bad.json").write_text("not json", encoding="utf-8")
        frames, _ = self.driver._load_animation("bad")
        assert frames == []


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_keys(self):
        d = _make_driver()
        st = d.status()
        assert "enabled" in st
        assert "ok" in st
        assert "backend" in st
        assert st["backend"] == "pi_ssd1306"
        assert "i2c_bus" in st
        assert "i2c_addr" in st

    def test_status_disabled(self):
        d = _make_driver()
        assert d.status()["enabled"] is False
        assert d.status()["ok"] is False
