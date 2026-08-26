from __future__ import annotations

from typing import Any, Dict, List


def get_perception_tool_definitions() -> List[Dict[str, Any]]:
    """Returns memory, map, vision, and social reasoning tool schemas for Agent Core."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "Search your episodic database for past events, dialogues, or seen people.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword"}
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_social_memory",
                "description": "Search a person's social memory: preferences, moments, and trust relationship.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person's name"},
                        "query": {
                            "type": "string",
                            "description": "Optional relevance filter",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_vision",
                "description": "Look through the camera and return recently detected objects/people.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_location",
                "description": "Get your current topological map location.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "pathfind",
                "description": "Finds a path from your current location to a known room/node.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Target map node name",
                        }
                    },
                    "required": ["destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_location",
                "description": "Update current location and learn it if it is a new place.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Current location name",
                        },
                    },
                    "required": ["location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "connect_locations",
                "description": "Connect two map locations and learn unknown nodes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "Source location",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination location",
                        },
                    },
                    "required": ["source", "destination"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_locations",
                "description": "List all known map locations.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_visual_context",
                "description": "Get the latest visual scene context: people, objects, hazards, and importance score. Returns cached result instantly.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_scene",
                "description": "Get a natural language description of what the camera currently sees.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember_person",
                "description": "Save or update a person in long-term memory with their relationship and recognition level (0=unknown, 1=seen, 2=familiar, 3=friend, 4=family, 5=owner).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person's name"},
                        "relationship": {
                            "type": "string",
                            "description": "Relationship: owner|family|friend|known|stranger",
                        },
                        "recognition_level": {
                            "type": "integer",
                            "description": "Recognition level 0-5",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_person_relationship",
                "description": "Update the relationship or recognition level of a known person by their ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "person_id": {
                            "type": "string",
                            "description": "Person's unique ID",
                        },
                        "relationship": {
                            "type": "string",
                            "description": "New relationship type",
                        },
                        "recognition_level": {
                            "type": "integer",
                            "description": "New recognition level 0-5",
                        },
                    },
                    "required": ["person_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_vlm_about_scene",
                "description": "Ask the vision-language model a specific question about the current camera view. Use for detailed analysis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Question about the scene in Turkish",
                        }
                    },
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "focus_person",
                "description": "Request the robot to look at (focus on) a specific person by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person's name (e.g., 'Emir', 'Alice')",
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "start_owner_follow",
                "description": "Start special owner-follow mode. Higher priority than regular follow mode. Robot will track the owner.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_follow",
                "description": "Stop any active follow mode (regular or owner).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]
