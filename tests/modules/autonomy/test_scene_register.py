"""Tests for SceneRegister (Peripheral Vision L1)."""

import time
import pytest
from modules.autonomy.services.scene_register import (
    SceneRegister,
    bbox_to_region,
    REGIONS_3X3,
)


def test_bbox_to_region_mapping():
    assert bbox_to_region(0.1, 0.1, 0.1, 0.1) == "top_left"
    assert bbox_to_region(0.4, 0.4, 0.2, 0.2) == "center"
    assert bbox_to_region(0.8, 0.8, 0.1, 0.1) == "bottom_right"
    assert bbox_to_region(0.1, 0.8, 0.1, 0.1) == "bottom_left"


def test_scene_register_people_tracking():
    reg = SceneRegister(window_s=2.0)
    reg.update_person("person_1", bbox=(0.8, 0.8, 0.1, 0.1), distance_m=1.8)

    state = reg.get_scene_state()
    assert len(state["people"]) == 1
    p = state["people"][0]
    assert p["id"] == "person_1"
    assert p["region"] == "bottom_right"
    assert p["distance_m"] == 1.8

    summary = reg.get_scene_summary()
    assert "person_1" in summary
    assert "sağ-alt (arka)" in summary


def test_scene_register_motion_and_sound():
    reg = SceneRegister(window_s=2.0)
    reg.update_motion_energy({"top_left": 0.85, "center": 0.1})
    reg.update_sound_event(direction_deg=135.0, salience=0.9)

    state = reg.get_scene_state()
    assert state["motion_energy"]["top_left"] == 0.85
    assert len(state["sound_events"]) == 1
    assert state["sound_events"][0]["direction_deg"] == 135.0

    assert not reg.is_region_clear("top_left")
    assert reg.is_region_clear("bottom_right")

    summary = reg.get_scene_summary()
    assert "135°" in summary
    assert "sol-üst" in summary


def test_scene_register_decay_and_pruning():
    reg = SceneRegister(window_s=0.2)
    reg.update_person("temp_person", region="mid_left")
    time.sleep(0.3)

    state = reg.get_scene_state()
    assert len(state["people"]) == 0
    assert reg.is_region_clear("mid_left")
    assert "boş" in reg.get_scene_summary().lower()
