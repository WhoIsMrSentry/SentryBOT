from __future__ import annotations

from modules.oled_faces.services.legacy_map import (
    OLED_LEGACY_COMPATIBILITY_CONTRACT,
    OLED_LEGACY_COMPATIBILITY_ROLE,
    FaceCommand,
    catalog_animations,
    catalog_moods,
    resolve_animation,
    resolve_bitmap,
    resolve_logo,
    resolve_mood,
)
from modules.oled_faces.services.mapper import (
    OLED_FACE_MAPPER_COMPATIBILITY_CONTRACT,
    FaceMapper,
)


def test_legacy_face_names_are_active_compatibility_aliases():
    assert OLED_LEGACY_COMPATIBILITY_CONTRACT is True
    assert OLED_LEGACY_COMPATIBILITY_ROLE == "active_face_name_alias_adapter"
    assert resolve_mood("normal") == "neutral"
    assert resolve_mood("battery_low") == "worried"
    assert resolve_mood("logo") == "attentive"
    assert "normal" in catalog_moods()
    assert "battery_low" in catalog_moods()


def test_legacy_animation_names_resolve_to_pip_engine_actions():
    assert "scan" in catalog_animations()
    assert resolve_animation("scan") == FaceCommand(activity="scanning")
    assert resolve_animation("blink") == FaceCommand(gesture="blink")
    assert resolve_animation("sleep") == FaceCommand(mood="sleepy", activity="idle")
    assert resolve_logo() == FaceCommand(mood="attentive", gesture="acknowledge")


def test_legacy_bitmap_gaze_aliases_preserve_gesture_intent():
    assert resolve_bitmap("look_left") == FaceCommand(mood="neutral", gesture="look_left")
    assert resolve_bitmap("wink_right") == FaceCommand(mood="neutral", gesture="wink_right")


def test_face_mapper_keeps_legacy_config_names_as_runtime_compatibility():
    assert OLED_FACE_MAPPER_COMPATIBILITY_CONTRACT is True
    mapper = FaceMapper({"idle_bitmap": "normal", "fallback_unknown": "warning"})
    idle = mapper.from_operational("idle")
    unknown = mapper.from_interaction_event("unknown.event")
    assert idle.mode == "bitmap"
    assert idle.name == "neutral"
    assert unknown.mode == "bitmap"
    assert unknown.name == "alert"
