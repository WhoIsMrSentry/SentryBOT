"""Tests for Pip eye engine (headless)."""
from __future__ import annotations

import time

import pytest

from modules.oled_faces.services.eyes.engine import EyeEngine
from modules.oled_faces.services.eyes.moods import MOODS
from modules.oled_faces.services.legacy_map import resolve_animation, resolve_bitmap, resolve_mood


def test_all_moods_render_headless():
    pytest.importorskip("PIL")
    frames = []

    def capture(img):
        frames.append(img)

    eng = EyeEngine(capture, fps=30)
    eng.start()
    try:
        for mood in MOODS:
            eng.set_mood(mood)
            time.sleep(0.05)
        assert len(frames) >= len(MOODS)
    finally:
        eng.stop()


def test_legacy_normal_maps_to_neutral():
    assert resolve_mood("normal") == "neutral"


def test_legacy_scan_animation_maps_to_scanning_activity():
    cmd = resolve_animation("scan")
    assert cmd.activity == "scanning"


def test_legacy_emotive_maps_to_listening_activity():
    cmd = resolve_animation("emotive")
    assert cmd.activity == "listening"


def test_legacy_bitmap_look_left_plays_gesture():
    cmd = resolve_bitmap("look_left")
    assert cmd.gesture == "look_left"
