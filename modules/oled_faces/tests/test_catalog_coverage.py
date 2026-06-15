"""Ensure every Pip motor entry is wired through config expansion."""
from __future__ import annotations

from modules.oled_faces.config_loader import load_config
from modules.oled_faces.services.catalog_registry import (
    MOTOR_ACTIVITIES,
    MOTOR_GESTURES,
    MOTOR_MOODS,
    build_catalog_pool,
    build_motor_event_map,
)


def test_motor_catalog_sizes():
    assert len(MOTOR_MOODS) == 31
    assert len(MOTOR_GESTURES) == 24
    assert len(MOTOR_ACTIVITIES) == 8


def test_full_catalog_pool_covers_motor():
    pool = build_catalog_pool()
    modes = {(i["mode"], i["name"]) for i in pool}
    for mood in MOTOR_MOODS:
        assert ("bitmap", mood) in modes
    for gesture in MOTOR_GESTURES:
        assert ("gesture", gesture) in modes
    for activity in MOTOR_ACTIVITIES:
        assert ("animation", activity) in modes
    assert len(pool) == 31 + 24 + 8


def test_expand_config_registers_every_motor_event():
    cfg = load_config()
    events = cfg.get("event_map") or {}
    for mood in MOTOR_MOODS:
        assert f"emotion:{mood}" in events
    for gesture in MOTOR_GESTURES:
        assert f"gesture:{gesture}" in events
    for activity in MOTOR_ACTIVITIES:
        assert f"activity:{activity}" in events


def test_idle_ambient_pool_includes_full_catalog():
    cfg = load_config()
    pool = (cfg.get("idle_ambient") or {}).get("pool") or []
    modes = {(str(i.get("mode", "")).lower(), str(i.get("name", "")).lower()) for i in pool if isinstance(i, dict)}
    assert len(modes) >= 31 + 24 + 8


def test_semantic_event_overrides_motor_defaults():
    raw_events = build_motor_event_map()
    cfg = load_config()
    events = cfg.get("event_map") or {}
    assert events["autonomy.excited"]["mode"] == "gesture"
    assert events["emotion:excitement"]["name"] == "wired"
    assert events["emotion:confusion"]["name"] == "disoriented"
    assert raw_events["emotion:neutral"]["name"] == "neutral"
