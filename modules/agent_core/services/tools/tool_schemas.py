from __future__ import annotations

from typing import Any, Dict, List

from .hardware_schemas import get_hardware_tool_definitions
from .perception_schemas import get_perception_tool_definitions



def _by_name(items: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for item in items:
        if item.get("function", {}).get("name") == name:
            return item
    raise KeyError(f"tool schema not found: {name}")


def get_all_tool_definitions() -> List[Dict[str, Any]]:
    """Returns safe tool schema specifications for Ollama / LLM function calling.

    Hardware schemas are selected through a safe allow-list. Physical movement and hazardous outputs must go through safety-reviewed action paths.
    """
    hw = get_hardware_tool_definitions()
    perception = get_perception_tool_definitions()
    ordered_names = [
        "move_head",
        "play_sound",
        "set_lights",
        "oled_face",
        "set_emotion",
        "interaction_event",
        "search_memory",
        "search_social_memory",
        "get_vision",
        "get_sensor_data",
        "get_location",
        "pathfind",
        "update_location",
        "connect_locations",
        "list_locations",
        "get_visual_context",
        "describe_scene",
        "remember_person",
        "update_person_relationship",
        "ask_vlm_about_scene",
        "focus_person",
        "start_owner_follow",
        "stop_follow",
        "speak",
        "queue_action",
        "get_action_status",
        "cancel_action",
        "express_emotion",
        "print_to_lcd",
        "get_last_rfid",
    ]
    lookup: Dict[str, Dict[str, Any]] = {}
    for item in hw + perception:
        name = item.get("function", {}).get("name")
        if name:
            lookup[name] = item
    return [lookup[name] for name in ordered_names if name in lookup]
