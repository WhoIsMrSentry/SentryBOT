"""Tests for Pip eye engine (headless)."""
from __future__ import annotations

import time

import pytest

from modules.visual_output.oled_faces.services.eyes.engine import EyeEngine
from modules.visual_output.oled_faces.services.eyes.moods import MOODS
from modules.visual_output.oled_faces.services.legacy_map import resolve_animation, resolve_bitmap, resolve_mood


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


def test_upstream_mood_catalog_size():
    assert len(MOODS) >= 32


def test_upstream_activities_ported():
    from modules.visual_output.oled_faces.services.eyes.activities import ACTIVITIES
    for name in ("debugging", "building", "testing", "deploying", "glitch", "ping_pong", "waiting", "chill"):
        assert name in ACTIVITIES or name in MOODS


def test_smoke_gesture_exists():
    from modules.visual_output.oled_faces.services.eyes.gestures import GESTURES_FN
    assert "smoke" in GESTURES_FN
    assert "acknowledge" in GESTURES_FN


def test_editing_activity_available():
    from modules.visual_output.oled_faces.services.eyes.activities import ACTIVITIES
    assert "editing" in ACTIVITIES
