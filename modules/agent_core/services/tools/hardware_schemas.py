from __future__ import annotations

from typing import Any, Dict, List

from .action_schemas import get_action_tool_definitions


def get_hardware_tool_definitions() -> List[Dict[str, Any]]:
    """Returns hardware control & action tool schemas for Agent Core."""
    actions = get_action_tool_definitions()
    return [
        {
            "type": "function",
            "function": {
                "name": "move_head",
                "description": "Move the robot's head to specific pan and tilt angles (0-180). 90 is center.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pan": {
                            "type": "integer",
                            "description": "Horizontal angle (0=Right, 90=Center, 180=Left)",
                        },
                        "tilt": {
                            "type": "integer",
                            "description": "Vertical angle (0=Down, 90=Center, 180=Up)",
                        },
                    },
                    "required": ["pan", "tilt"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_sound",
                "description": "Play an audio file from the SD card (e.g., 'alert_1.mp3', 'start.wav').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the audio file",
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_lights",
                "description": "Set the Neopixel body lights to a specific effect and color.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "effect": {
                            "type": "string",
                            "enum": [
                                "COMET",
                                "PULSE",
                                "WAVE",
                                "SOLID",
                                "OFF",
                                "BREATHE",
                                "RANDOM_BLINK",
                                "TWINKLE",
                            ],
                            "description": "The animation effect",
                        },
                        "color": {
                            "description": "RGB array like [255, 0, 0] or a common color name such as red, green, blue, yellow, purple, white, off.",
                            "anyOf": [
                                {
                                    "type": "array",
                                    "items": {"type": "integer", "minimum": 0, "maximum": 255},
                                    "minItems": 3,
                                    "maxItems": 3,
                                },
                                {
                                    "type": "string",
                                    "enum": ["red", "green", "blue", "yellow", "orange", "purple", "pink", "cyan", "white", "off"],
                                },
                            ],
                        },
                    },
                    "required": ["effect"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "oled_face",
                "description": "Change the expression on the OLED eyes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "enum": [
                                "Alert",
                                "Angry",
                                "Bored",
                                "Happy",
                                "Sad",
                                "ScanningEyes",
                                "Winking",
                                "look_up",
                                "normal",
                                "logo",
                                "scan",
                                "blink",
                                "emotive",
                            ],
                            "description": "The emotion or animation to display on the eyes",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_emotion",
                "description": "Express a canonical emotion across OLED face, NeoPixel lights, and robot state.",
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
                            ],
                            "description": "Canonical emotion from the shared vocabulary",
                        }
                    },
                    "required": ["emotion"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "interaction_event",
                "description": "Trigger a pre-programmed complex interaction/animation sequence.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event": {
                            "type": "string",
                            "enum": [
                                "autonomy.excited",
                                "autonomy.bored",
                                "autonomy.monologue",
                                "autonomy.look_around",
                                "autonomy.blink",
                                "autonomy.stretch",
                                "autonomy.sleep",
                                "autonomy.wake",
                            ],
                            "description": "The interaction event to emit",
                        }
                    },
                    "required": ["event"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sensor_data",
                "description": "Get current battery level and ultrasonic distance measurements.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        actions[0],  # speak
        actions[1],  # queue_action
        actions[2],  # get_action_status
        actions[3],  # cancel_action
        actions[4],  # express_emotion
        {
            "type": "function",
            "function": {
                "name": "print_to_lcd",
                "description": "Write text to the robot's front LCD screen. Used to display short messages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "top": {
                            "type": "string",
                            "description": "Text for the top line (max 16 chars).",
                        },
                        "bottom": {
                            "type": "string",
                            "description": "Text for the bottom line (max 16 chars).",
                        },
                    },
                    "required": ["top", "bottom"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_last_rfid",
                "description": "Get the UID of the last scanned RFID tag. Useful to check who last interacted with the robot.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]
