from __future__ import annotations

from typing import Any, Dict, List


def get_action_tool_definitions() -> List[Dict[str, Any]]:
    """Returns emotion expression, speech synthesis, and action arbitration tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": "speak",
                "description": (
                    "Say the given text out loud through the robot's speaker (TTS). "
                    "Use this when the user asks the robot to say/repeat something "
                    "('şunu söyle', 'say this') or when speech itself is the action."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Exact text to speak out loud.",
                        },
                        "tone": {
                            "type": "string",
                            "description": "Optional emotional tone based on internal state (e.g. neutral, happy, sad, excited, tired, calm). Use this to reflect your mood.",
                        },
                        "language": {
                            "type": "string",
                            "description": "Optional BCP-47/ISO language code of the text (e.g. tr, en, de).",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "queue_action",
                "description": "Submit an action (lights, sound, animation, etc.) to the action arbiter with priority and TTL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_type": {
                            "type": "string",
                            "description": "Type of action: head_move, speak, lights, animation, sound, etc.",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Priority 0-100. Higher wins. Default 50.",
                        },
                        "ttl_ms": {
                            "type": "integer",
                            "description": "Time-to-live in milliseconds. Default 5000.",
                        },
                        "payload": {
                            "type": "object",
                            "description": "Action-specific parameters (optional)",
                        },
                    },
                    "required": ["action_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_action_status",
                "description": "Get current action arbiter and speech arbiter status.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_action",
                "description": "Cancel a queued action by action_id.",
                "parameters": {
                    "type": "object",
                    "properties": {"action_id": {"type": "string"}},
                    "required": ["action_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "express_emotion",
                "description": (
                    "Express a canonical emotion across all modalities atomically. "
                    "Coordinates NeoPixel LEDs (effect+color+speed), OLED faces (animation), "
                    "TTS voice (tone+pitch+speed), head servos (pan/tilt), and ear servos "
                    "to produce a UNIFIED, semantically-grounded expression. "
                    "Use this for genuine emotional reactions — the LLM should call this "
                    "tool whenever it 'feels' something, instead of just describing it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "enum": [
                                "neutral",
                                "joy",
                                "sadness",
                                "anger",
                                "furious",
                                "fear",
                                "surprise",
                                "excitement",
                                "love",
                                "disgust",
                                "confusion",
                                "worried",
                                "bored",
                                "tired",
                                "curiosity",
                                "calm",
                                "pride",
                                "embarrassment",
                                "awe",
                                "gloomy",
                                "cool",
                                "devil",
                                "kawaii",
                                "dead",
                                "smoking",
                                "wired",
                                "nervous",
                                "disoriented",
                                "suspicious",
                            ],
                            "description": "Canonical emotion name. Aliases like 'happy'='joy', 'sad'='sadness', 'kork'='fear' also work.",
                        },
                        "intensity": {
                            "type": "number",
                            "minimum": 0.1,
                            "maximum": 2.0,
                            "default": 1.0,
                            "description": "Expression intensity: 0.1=subtle, 1.0=normal, 2.0=extreme.",
                        },
                        "duration_s": {
                            "type": "number",
                            "minimum": 0.5,
                            "maximum": 30.0,
                            "default": 3.0,
                            "description": "How long to hold the expression in seconds.",
                        },
                        "modalities": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["leds", "oled", "voice", "head", "ears"],
                            },
                            "default": ["leds", "oled", "voice", "head"],
                            "description": "Which output modalities to activate. Default: all.",
                        },
                        "text": {
                            "type": "string",
                            "description": "Optional text to speak (requires 'voice' in modalities).",
                        },
                        "language": {
                            "type": "string",
                            "default": "tr",
                            "description": "BCP-47 language code (e.g. tr, en, de).",
                        },
                    },
                    "required": ["emotion"],
                },
            },
        },
    ]
