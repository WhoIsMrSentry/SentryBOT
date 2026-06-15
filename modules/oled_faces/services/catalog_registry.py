"""Motor catalog (moods / gestures / activities) and config expansion helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .eyes.activities import ACTIVITIES
from .eyes.gestures import BLINKS, GESTURES_FN
from .eyes.moods import MOODS
from .mapper import OledAction

# 31 moods, 24 gestures (7 blinks + 17 moves), 8 busy activities (+ idle)
MOTOR_MOODS: Tuple[str, ...] = tuple(MOODS.keys())
MOTOR_GESTURES: Tuple[str, ...] = tuple(BLINKS) + tuple(GESTURES_FN)
MOTOR_ACTIVITIES: Tuple[str, ...] = tuple(a for a in ACTIVITIES if a != "idle")


def build_catalog_pool() -> List[Dict[str, str]]:
    """Flat playlist covering every motor entry (idle ambient round-robin)."""
    items: List[Dict[str, str]] = []
    for mood in MOTOR_MOODS:
        items.append({"mode": "bitmap", "name": mood})
    for gesture in MOTOR_GESTURES:
        items.append({"mode": "gesture", "name": gesture})
    for activity in MOTOR_ACTIVITIES:
        items.append({"mode": "animation", "name": activity})
    return items


def build_motor_event_map() -> Dict[str, Dict[str, str]]:
    """Default event_map entries so every motor name is addressable as an event."""
    out: Dict[str, Dict[str, str]] = {}
    for mood in MOTOR_MOODS:
        out[f"emotion:{mood}"] = {"mode": "bitmap", "name": mood}
    for gesture in MOTOR_GESTURES:
        out[f"gesture:{gesture}"] = {"mode": "gesture", "name": gesture}
    for activity in MOTOR_ACTIVITIES:
        out[f"activity:{activity}"] = {"mode": "animation", "name": activity}
    return out


def expand_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge motor catalog into event_map and idle_ambient pool (config overrides win)."""
    merged = dict(cfg)
    motor_events = build_motor_event_map()
    user_events = dict(merged.get("event_map") or {})
    merged["event_map"] = {**motor_events, **user_events}

    ambient = dict(merged.get("idle_ambient") or {})
    if bool(ambient.get("use_full_catalog", True)):
        user_pool = list(ambient.get("pool") or [])
        seen = {(str(i.get("mode", "")).lower(), str(i.get("name", "")).lower()) for i in user_pool if isinstance(i, dict)}
        pool = list(user_pool)
        for item in build_catalog_pool():
            key = (item["mode"], item["name"])
            if key not in seen:
                pool.append(item)
                seen.add(key)
        ambient["pool"] = pool
    merged["idle_ambient"] = ambient
    return merged


def catalog_pool_actions() -> List[OledAction]:
    return [
        OledAction(mode=str(i["mode"]), name=str(i["name"]))
        for i in build_catalog_pool()
    ]


__all__ = [
    "MOTOR_MOODS",
    "MOTOR_GESTURES",
    "MOTOR_ACTIVITIES",
    "build_catalog_pool",
    "build_motor_event_map",
    "expand_config",
    "catalog_pool_actions",
]
