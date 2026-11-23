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
                            "description": "Text for the top line (max 20 chars).",
                        },
                        "bottom": {
                            "type": "string",
                            "description": "Text for the bottom line (max 20 chars).",
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
        {
            "type": "function",
            "function": {
                "name": "robot_posture",
                "description": "Change the robot's physical leg posture (stand up, sit down, home pose, or emergency stop).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "posture": {
                            "type": "string",
                            "enum": ["stand", "sit", "home", "estop"],
                            "description": "Target physical posture command.",
                        }
                    },
                    "required": ["posture"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "move_body",
                "description": "Move the robot body/legs forward, backward, turn left/right, or stop immediately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["forward", "backward", "left", "right", "stop"],
                            "description": "Movement direction.",
                        },
                        "speed": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "default": 60,
                            "description": "Motion speed (clamped safely).",
                        },
                        "steps": {
                            "type": "integer",
                            "minimum": 20,
                            "maximum": 2000,
                            "default": 200,
                            "description": "Step distance for left/right turns.",
                        },
                    },
                    "required": ["direction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_laser",
                "description": "Safely control the robot's dual pointer lasers through SafetyFilter (auto-offs after max safe duration).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": ["on", "off"],
                            "description": "Turn laser(s) on or off.",
                        },
                        "target": {
                            "type": "string",
                            "enum": ["both", "left", "right"],
                            "default": "both",
                            "description": "Which laser module to control.",
                        },
                        "duration_s": {
                            "type": "number",
                            "minimum": 0.2,
                            "maximum": 5.0,
                            "default": 2.0,
                            "description": "Auto-off safety duration in seconds.",
                        },
                    },
                    "required": ["state"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "move_ears",
                "description": "Move the robot's left and right ear servos (0-180 deg) or run an ear gesture.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "left": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 180,
                            "description": "Left ear angle (optional if gesture is set).",
                        },
                        "right": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 180,
                            "description": "Right ear angle (optional if gesture is set).",
                        },
                        "gesture": {
                            "type": "string",
                            "enum": ["wakeword", "sound", "vigilance", "relax", "idle"],
                            "description": "Predefined ear gesture preset.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_buzzer",
                "description": "Play an Arduino buzzer tone or named cute chime effect.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "frequency": {
                            "type": "integer",
                            "minimum": 100,
                            "maximum": 10000,
                            "default": 2200,
                            "description": "Tone frequency in Hz.",
                        },
                        "duration_ms": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 2000,
                            "default": 80,
                            "description": "Beep duration in milliseconds.",
                        },
                        "cute_sound": {
                            "type": "string",
                            "description": "Optional named cute sound (e.g. happy, alert, wake, sad).",
                        },
                    },
                },
            },
        },
    ]
