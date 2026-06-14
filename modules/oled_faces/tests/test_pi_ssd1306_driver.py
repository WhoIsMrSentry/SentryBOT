"""Unit tests for PiSsd1306Driver (non-hardware paths)."""
from __future__ import annotations

import pytest

from modules.oled_faces.services.pi_ssd1306_driver import PiSsd1306Driver


def _make_driver(enabled: bool = False) -> PiSsd1306Driver:
    return PiSsd1306Driver({"enabled": enabled})


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
        assert d._buffer[0] & 0x01

    def test_set_pixel_out_of_bounds_is_noop(self):
        d = _make_driver()
        d.clear()
        d.set_pixel(-1, 0)
        d.set_pixel(d.width, 0)
        assert all(b == 0 for b in d._buffer)

    def test_buffer_size(self):
        d = _make_driver()
        assert len(d._buffer) == (d.width * d.height) // 8


class TestPilConversion:
    def test_pil_image_sets_pixels(self):
        pytest.importorskip("PIL")
        from PIL import Image

        d = _make_driver()
        d._ok = True
        img = Image.new("1", (128, 64), 0)
        px = img.load()
        px[10, 5] = 1
        d._pil_to_buffer(img)
        assert d._buffer  # smoke: conversion runs without error


class TestStatus:
    def test_status_keys(self):
        d = _make_driver()
        st = d.status()
        assert st["backend"] == "pi_ssd1306"
        assert st["enabled"] is False
