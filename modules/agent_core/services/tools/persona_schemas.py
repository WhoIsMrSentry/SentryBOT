"""JSON schemas for Agent Core persona & character lore RAG tools."""
from __future__ import annotations

from typing import Any, Dict, List


def get_persona_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "set_persona",
                "description": (
                    "Switch the robot's active character persona (e.g. 'glados', 'sentry'). "
                    "Isolates conversational memory per persona while keeping physical robot control."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Persona id or alias, e.g. 'glados' or 'sentry'.",
                        },
                        "response_language": {
                            "type": "string",
                            "description": "Optional reply language override: '' / 'follow_user', 'tr', or 'en'.",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_personas",
                "description": "List all available character personas and show which persona is currently active.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_persona_knowledge",
                "description": (
                    "Search the active character persona's local lore/wiki RAG database for background facts, "
                    "character history, or universe references."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic, entity, or question to look up in persona lore.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of lore chunks to return (1-6, default 3).",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]


__all__ = ["get_persona_tool_definitions"]
