# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_llm_tool_registry'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime capabilities and execution: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ToolRegistry remains an LLM-facing proposal surface. Physical actions must still pass through action/safety/capability paths.'
# --- End SentryBOT safety/action boundary contract ---

import json
import logging
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger("agent.tools")


class HttpClient:
    """Shared HTTP client for gateway communication."""

    def __init__(self, gateway_base_url: str, default_timeout: float = 2.0):
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._default_timeout = default_timeout

    def _url(self, path: str) -> str:
        return f"{self._gateway_base_url}/{str(path).lstrip('/')}"

    def get(self, path: str, timeout: Optional[float] = None) -> requests.Response:
        return requests.get(self._url(path), timeout=timeout or self._default_timeout)

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> requests.Response:
        return requests.post(self._url(path), json=json_data or {}, timeout=timeout or self._default_timeout)

    def _handle_response(self, resp: requests.Response, error_prefix: str = "Request") -> str:
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {}
        return f"{error_prefix} failed: HTTP {resp.status_code}"


class ToolRegistry:
    """
    Registers Python functions as native tools for the LLM.
    Provides the JSON schemas for Ollama.
    """

    def __init__(
        self,
        client,
        memory,
        slam,
        world_state,
        safety_filter,
        tool_execution_arbiter=None,
        vision_arbiter=None,
        vlm_ask_timeout_s: float = 22.0,
        gateway_base_url: str = "",
    ):
        self.client = client
        self.memory = memory
        self.slam = slam
        self.world_state = world_state
        self.safety = safety_filter
        self.tool_execution_arbiter = tool_execution_arbiter
        self.vision_arbiter = vision_arbiter
        self.vlm_ask_timeout_s = float(vlm_ask_timeout_s)
        if gateway_base_url:
            gw = str(gateway_base_url).rstrip("/")
        else:
            try:
                from modules.gateway.url import resolve_gateway_base_url

                gw = resolve_gateway_base_url()
            except Exception:
                gw = "http://127.0.0.1:8080"
        self._gateway_base_url = gw
        self._http = HttpClient(gw)
        self.status_hook: Optional[Callable[[Dict[str, Any]], None]] = None

        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

        self._register_all()

    # ── Vision arbitration helpers ───────────────────────────────────
    _VLM_TOOL_NAMES: frozenset = frozenset(
        {
            "get_vision",
            "get_visual_context",
            "describe_scene",
            "ask_vlm_about_scene",
            "focus_person",
        }
    )

    def _url(self, path: str) -> str:
        return f"{self._gateway_base_url}/{str(path).lstrip('/')}"

    def _camera_input_available(self) -> bool:
        try:
            from modules.common.vision_availability import camera_live_available

            return camera_live_available(self._gateway_base_url, timeout_s=0.5)
        except Exception:
            return False

    def _vision_input_available(self) -> bool:
        try:
            from modules.common.vision_availability import vision_input_available

            return vision_input_available(self._gateway_base_url, timeout_s=0.6)
        except Exception:
            return False

    def _vision_unavailable_message(self) -> str:
        return "Görüş verisi şu an kullanılamıyor (kamera veya uzak VLM cache yok); görme araçları devre dışı."

    def _acquire_vision(self, tool_name: str) -> bool:
        if self.vision_arbiter is None or tool_name not in self._VLM_TOOL_NAMES:
            return True
        try:
            return bool(self.vision_arbiter.acquire(f"tool:{tool_name}", ttl_s=20.0))
        except Exception:
            return True

    def _release_vision(self, tool_name: str) -> None:
        if self.vision_arbiter is None or tool_name not in self._VLM_TOOL_NAMES:
            return
        try:
            self.vision_arbiter.release(f"tool:{tool_name}")
        except Exception:
            pass

    def _register(self, func: Callable, schema: Dict[str, Any]):
        name = schema["function"]["name"]
        self.tools[name] = func
        self.schemas.append(schema)

    def execute(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Executes the mapped tool and returns the string result."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."

        acquired = False
        vision_held = False
        try:
            if self.tool_execution_arbiter is not None:
                if not self.tool_execution_arbiter.acquire(tool_name):
                    self._emit_status(
                        {
                            "type": "tool_error",
                            "tool": tool_name,
                            "error": "resource_busy",
                        }
                    )
                    return f"Error executing {tool_name}: resource busy"
                acquired = True
            if tool_name in self._VLM_TOOL_NAMES and not self._vision_input_available():
                self._emit_status(
                    {
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": "camera_unavailable",
                    }
                )
                return self._vision_unavailable_message()
            if not self._acquire_vision(tool_name):
                self._emit_status(
                    {
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": "vision_busy",
                    }
                )
                return f"Error executing {tool_name}: vision arbiter busy"
            vision_held = tool_name in self._VLM_TOOL_NAMES
            logger.info(f"LLM called tool: {tool_name}({kwargs})")
            result = self.tools[tool_name](**kwargs)
            result_str = (
                json.dumps(result) if isinstance(result, (dict, list)) else str(result)
            )
            self._emit_status(
                {
                    "type": "tool_done",
                    "tool": tool_name,
                    "result": result_str,
                }
            )
            return result_str
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            self._emit_status(
                {"type": "tool_error", "tool": tool_name, "error": str(e)}
            )
            return f"Error executing {tool_name}: {e}"
        finally:
            if vision_held:
                self._release_vision(tool_name)
            if acquired and self.tool_execution_arbiter is not None:
                self.tool_execution_arbiter.release(tool_name)

    def _emit_status(self, payload: Dict[str, Any]) -> None:
        hook = self.status_hook
        if not hook:
            return
        try:
            hook(payload)
        except Exception:
            pass

    def get_tool_schema(self, include: List[str] | None = None) -> List[Dict[str, Any]]:
        """Returns all tool schemas or only a selected subset by tool name."""
        if not include:
            return self.schemas

        include_set = {str(name) for name in include if str(name) in self.tools}
        return [
            schema
            for schema in self.schemas
            if schema.get("function", {}).get("name") in include_set
        ]

    def get_tool_names(self) -> List[str]:
        return list(self.tools.keys())

    # ==========================================
    # TOOL IMPLEMENTATIONS & SCHEMAS
    # ==========================================

    def _register_all(self):
        self._register(
            self.move_head,
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
        )

        self._register(
            self.play_sound,
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
        )

        self._register(
            self.set_lights,
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
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "RGB color array like [255, 0, 0] for red",
                            },
                        },
                        "required": ["effect"],
                    },
                },
            },
        )

        self._register(
            self.set_laser,
            {
                "type": "function",
                "function": {
                    "name": "set_laser",
                    "description": "Turn the targeting laser on or off.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "on": {
                                "type": "boolean",
                                "description": "True to turn on, False to turn off",
                            }
                        },
                        "required": ["on"],
                    },
                },
            },
        )

        self._register(
            self.oled_face,
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
        )

        self._register(
            self.set_emotion,
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
        )

        self._register(
            self.interaction_event,
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
        )

        self._register(
            self.search_memory,
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
        )

        self._register(
            self.search_social_memory,
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
        )

        self._register(
            self.get_vision,
            {
                "type": "function",
                "function": {
                    "name": "get_vision",
                    "description": "Look through the camera and return recently detected objects/people.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.get_sensor_data,
            {
                "type": "function",
                "function": {
                    "name": "get_sensor_data",
                    "description": "Get current battery level and ultrasonic distance measurements.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.get_location,
            {
                "type": "function",
                "function": {
                    "name": "get_location",
                    "description": "Get your current topological map location.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.pathfind,
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
        )

        self._register(
            self.update_location,
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
        )

        self._register(
            self.connect_locations,
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
        )

        self._register(
            self.list_locations,
            {
                "type": "function",
                "function": {
                    "name": "list_locations",
                    "description": "List all known map locations.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        # ── Living Vision Agent tools ─────────────────────────────
        self._register(
            self.get_visual_context,
            {
                "type": "function",
                "function": {
                    "name": "get_visual_context",
                    "description": "Get the latest visual scene context: people, objects, hazards, and importance score. Returns cached result instantly.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.describe_scene,
            {
                "type": "function",
                "function": {
                    "name": "describe_scene",
                    "description": "Get a natural language description of what the camera currently sees.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.remember_person,
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
        )

        self._register(
            self.update_person_relationship,
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
        )

        self._register(
            self.ask_vlm_about_scene,
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
        )

        self._register(
            self.focus_person,
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
        )

        self._register(
            self.start_owner_follow,
            {
                "type": "function",
                "function": {
                    "name": "start_owner_follow",
                    "description": "Start special owner-follow mode. Higher priority than regular follow mode. Robot will track the owner.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        )

        self._register(
            self.stop_follow,
            {
                "type": "function",
                "function": {
                    "name": "stop_follow",
                    "description": "Stop any active follow mode (regular or owner).",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        )

        self._register(
            self.speak,
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
                                "description": "Optional emotional tone (e.g. neutral, happy, sad, excited, calm).",
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
        )

        self._register(
            self.queue_action,
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
        )

        self._register(
            self.get_action_status,
            {
                "type": "function",
                "function": {
                    "name": "get_action_status",
                    "description": "Get current action arbiter and speech arbiter status.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        self._register(
            self.cancel_action,
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
        )

        self._register(
            self.express_emotion,
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
                                    "neutral", "joy", "sadness", "anger", "furious", "fear",
                                    "surprise", "excitement", "love", "disgust", "confusion",
                                    "worried", "bored", "tired", "curiosity", "calm", "pride",
                                    "embarrassment", "awe", "gloomy", "cool", "devil", "kawaii",
                                    "dead", "smoking", "wired", "nervous", "disoriented",
                                    "suspicious"
                                ],
                                "description": "Canonical emotion name. Aliases like 'happy'='joy', 'sad'='sadness', 'kork'='fear' also work.",
                            },
                            "intensity": {
                                "type": "number",
                                "minimum": 0.1, "maximum": 2.0,
                                "default": 1.0,
                                "description": "Expression intensity: 0.1=subtle, 1.0=normal, 2.0=extreme.",
                            },
                            "duration_s": {
                                "type": "number",
                                "minimum": 0.5, "maximum": 30.0,
                                "default": 3.0,
                                "description": "How long to hold the expression in seconds.",
                            },
                            "modalities": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["leds", "oled", "voice", "head", "ears"]},
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
        )

    # ==========================================
    # TOOL LOGIC
    # ==========================================

    def move_head(self, pan: int, tilt: int) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        safe_pan = self.safety.clamp_servo(pan)
        safe_tilt = self.safety.clamp_servo(tilt)
        resp = self.client.move_head(safe_pan, safe_tilt)
        return (
            f"Head moved to pan={safe_pan}, tilt={safe_tilt}. Hardware response: {resp}"
        )

    def play_sound(self, name: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        resp = self.client.play_sound(name)
        return f"Playing sound: {name}. Response: {resp}"

    def set_lights(self, effect: str, color: List[int] = None) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        r, g, b = (0, 0, 0)
        if color and len(color) == 3:
            r, g, b = color

        if effect.upper() == "SOLID":
            self.client.fill_neopixel_color(r, g, b)
            return f"Lights set to solid RGB({r},{g},{b})"
        elif effect.upper() == "OFF":
            self.client.fill_neopixel_color(0, 0, 0)
            return "Lights turned off"
        else:
            self.client.set_neopixel(effect.upper(), color=[r, g, b] if color else None)
            return f"Playing light effect: {effect.upper()}"

    def set_laser(self, on: bool) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        resp = self.client.set_laser(on=on)
        return f"Laser turned {'ON' if on else 'OFF'}. Response: {resp}"

    def oled_face(self, expression: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        key = str(expression or "").strip().lower()
        pip_activities = {
            "listening",
            "thinking",
            "scanning",
            "searching",
            "working",
            "processing",
            "connecting",
            "sleep",
            "alert",
        }
        legacy_anims = {"scan", "emotive", "blink", "wink", "all", "icons"}
        if key in pip_activities or key in legacy_anims:
            resp = self.client.oled_anim(key)
        else:
            resp = self.client.oled_show(key)
        return f"OLED face updated to {expression}. Response: {resp}"

    def set_emotion(self, emotion: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            from modules.common.emotion_vocab import emotion_render

            render = emotion_render(emotion)
            canon = render.canonical
        except Exception:
            canon = str(emotion or "neutral").strip().lower()
            render = None
        self.client.update_emotions([canon])
        if render is not None:
            self.client.set_neopixel(
                render.effect, emotions=[canon], color=list(render.rgb)
            )
            self.client.oled_show(render.oled)
            self.client.push_interaction_event(f"emotion:{canon}")
            return f"Expressed emotion: {canon}"
        self.client.push_interaction_event(f"emotion:{canon}")
        return f"Internal emotion set to: {canon}"

    def interaction_event(self, event: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        self.client.push_interaction_event(event)
        return f"Triggered complex interaction event: {event}"

    def search_memory(self, query: str) -> str:
        res = self.memory.search_memory(query, limit=5)
        if not res:
            return "No matching memories found."
        return str(res)

    def search_social_memory(self, name: str, query: str = "") -> str:
        try:
            from modules.social_db import get_default as _social_default

            db = _social_default()
        except Exception:
            return "Social memory unavailable."
        if db is None:
            return "Social memory unavailable."
        rec = db.persons.get_by_name(str(name or "").strip())
        if not rec:
            return f"No social record for {name}."
        pid = rec["id"]
        grouped = db.relationships.list_grouped(pid)
        moments = db.moments.top_for_person(pid, limit=10)
        snippets = [
            str(m.get("text", "")).strip()
            for m in moments
            if str(m.get("text", "")).strip()
        ]
        q = str(query or "").strip()
        if q and snippets:
            try:
                from .semantic_index import rank

                ranked = rank(q, snippets, top_k=3)
                snippets = [snippets[idx] for idx, _ in ranked if idx < len(snippets)]
            except Exception:
                pass
        parts: List[str] = []
        trust = float(rec.get("trust_score", 0.0) or 0.0)
        parts.append(f"trust_score={trust:.2f}")
        for key in ("likes", "dislikes", "topics"):
            vals = (
                grouped.get(key, []) if isinstance(grouped.get(key, []), list) else []
            )
            if vals:
                parts.append(f"{key}: {', '.join(str(v) for v in vals[:6])}")
        if snippets:
            parts.append("moments: " + " | ".join(snippets[:3]))
        return "\n".join(parts) if parts else "No social memories found."

    def get_vision(self) -> str:
        if not self.client:
            return "Error: Vision client disconnected."
        results = self.client.get_latest_vision_results(limit=5)
        if not results:
            return "Vision results unavailable. Continue with text-only reasoning if needed."
        return f"Vision: {results}"

    def get_sensor_data(self) -> str:
        bat = self.world_state.get_state().get("battery_percent", "unknown")
        dist_info = "Distance unknown"
        if self.client:
            ultra = self.client.read_sensor("ultra_read")
            if ultra and "cm" in str(ultra):  # Example check, actual parsing may vary
                dist_info = f"Obstacle at {ultra}"
        return f"Battery: {bat}%. {dist_info}"

    def get_location(self) -> str:
        loc = self.slam.get_location()
        return f"You are currently at: {loc}"

    def pathfind(self, destination: str) -> str:
        path = self.slam.pathfind(destination)
        if not path:
            return f"Cannot find path to {destination}."
        return f"Path to {destination}: {' -> '.join(path)}"

    def update_location(self, location: str) -> str:
        ok = self.slam.update_location(location)
        if not ok:
            return f"Failed to update location: {location}"
        return f"Current location updated to: {self.slam.get_location()}"

    def connect_locations(self, source: str, destination: str) -> str:
        ok = self.slam.connect_nodes(source, destination, bidirectional=True)
        if not ok:
            return f"Failed to connect '{source}' and '{destination}'."
        return f"Connected locations: {source} <-> {destination}"

    def list_locations(self) -> str:
        known = self.slam.known_locations()
        if not known:
            return "No known locations yet."
        return f"Known locations: {', '.join(known)}"

    # ── Living Vision Agent tool implementations ─────────────────

    def get_visual_context(self) -> str:
        """Return the latest cached visual context."""
        if not self.client:
            return "Error: Vision client disconnected."
        try:
            resp = self._http.get("vlm/context/latest", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("available"):
                    ctx = data.get("context", {})
                    parts = []
                    if ctx.get("summary"):
                        parts.append(f"Scene: {ctx['summary']}")
                    people = ctx.get("people", [])
                    if people:
                        names = [p.get("name", "Unknown") for p in people]
                        parts.append(f"People: {', '.join(names)}")
                    hazards = ctx.get("hazards", [])
                    if hazards:
                        parts.append(f"Hazards: {hazards}")
                    parts.append(f"Importance: {ctx.get('importance_score', 0.0)}")
                    return " | ".join(parts) if parts else "Scene is empty."
                refresh = self._http.post("vlm/context/refresh", timeout=8.0)
                if refresh.status_code == 200:
                    rdata = refresh.json()
                    rctx = rdata.get("context") or {}
                    if rctx:
                        summary = rctx.get("summary", "")
                        return (
                            f"Scene: {summary}"
                            if summary
                            else "Visual context refreshed."
                        )
                return "No visual context available yet. Camera may not be active."
            return "Vision context endpoint returned error."
        except Exception as exc:
            return f"Failed to get visual context: {exc}"

    def describe_scene(self) -> str:
        """Get a natural language scene description."""
        if not self.client:
            return "Error: Vision client disconnected."
        try:
            resp = self._http.get("vlm/context/latest", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                ctx = data.get("context", {})
                interpretation = ctx.get("persona_interpretation") or ctx.get("summary")
                if interpretation:
                    return interpretation
                return ctx.get("raw_vlm_observation", "No scene description available.")
            return "Scene description not available."
        except Exception as exc:
            return f"Failed to describe scene: {exc}"

    def remember_person(
        self, name: str, relationship: str = "known", recognition_level: int = 2
    ) -> str:
        """Save or update a person in memory."""
        try:
            resp = self._http.post(
                "vlm/person/remember",
                json_data={
                    "name": name,
                    "relationship": relationship,
                    "recognition_level": recognition_level,
                },
                timeout=2.0,
            )
            if resp.status_code == 200:
                return (
                    f"Remembered {name} as {relationship} (level {recognition_level})."
                )
            return f"Failed to remember person: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Failed to remember person: {exc}"

    def update_person_relationship(
        self, person_id: str, relationship: str = "", recognition_level: int = -1
    ) -> str:
        """Update a person's relationship or level."""
        try:
            resp = self._http.post(
                "vlm/person/relationship",
                json_data={
                    "person_id": person_id,
                    "relationship": relationship,
                    "recognition_level": recognition_level,
                },
                timeout=2.0,
            )
            if resp.status_code == 200:
                return f"Updated person {person_id}."
            return f"Failed to update person: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Failed to update person: {exc}"

    def ask_vlm_about_scene(self, question: str) -> str:
        """Ask the VLM a question about the current camera view."""
        try:
            resp = self._http.post(
                "vlm/ask",
                json_data={"question": question},
                timeout=max(2.0, float(self.vlm_ask_timeout_s)),
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("answer", "No answer from VLM.")
            return f"VLM question failed: HTTP {resp.status_code}"
        except Exception as exc:
            try:
                ctx_resp = self._http.get("vlm/context/latest", timeout=2.0)
                if ctx_resp.status_code == 200:
                    data = ctx_resp.json()
                    if data.get("available"):
                        ctx = data.get("context", {})
                        summary = (
                            str(ctx.get("summary", "")).strip()
                            or str(ctx.get("persona_interpretation", "")).strip()
                        )
                        if summary:
                            return f"Görüntü işleme gecikti; elimdeki son görüntüye göre {summary}"
            except Exception:
                pass
            return f"Görüntü işleme gecikti; elimdeki son görüntüye göre konuşuyorum. ({exc})"

    def focus_person(self, name: str) -> str:
        """Request the robot to focus on (look at) a specific person."""
        try:
            resp = self._http.post(
                "vlm/focus/person",
                json_data={"name": name},
                timeout=2.0,
            )
            if resp.status_code == 200:
                return f"Focusing on {name}."
            return f"Focus request failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Focus failed: {exc}"

    def start_owner_follow(self) -> str:
        """Start special owner-follow mode (higher priority than regular follow)."""
        try:
            resp = self._http.post("vlm/follow/owner/start", timeout=2.0)
            if resp.status_code == 200:
                return "Owner follow mode activated."
            return f"Owner follow failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Owner follow failed: {exc}"

    def stop_follow(self) -> str:
        """Stop any active follow mode."""
        try:
            resp = self._http.post("vlm/follow/stop", timeout=2.0)
            if resp.status_code == 200:
                return "Follow mode stopped."
            return f"Stop follow failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Stop follow failed: {exc}"

    def speak(self, text: str, tone: str = "", language: str = "") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return "Error: nothing to speak."
        payload: Dict[str, Any] = {"text": cleaned}
        if tone:
            payload["tone"] = str(tone).strip().lower()
        if language:
            payload["language"] = str(language).strip().lower()
        result = self.queue_action("speak", priority=60, ttl_ms=10000, payload=payload)
        if result.startswith("Action queued"):
            return f"Speaking: {cleaned[:80]}"
        return result

    def queue_action(
        self,
        action_type: str,
        priority: int = 50,
        ttl_ms: int = 5000,
        payload: dict = None,
    ) -> str:
        """Submit an action to the action arbiter."""
        if payload is None:
            payload = {}
        try:
            resp = self._http.post(
                "agent/actions/queue",
                json_data={
                    "type": action_type,
                    "priority": priority,
                    "ttl_ms": ttl_ms,
                    "payload": payload,
                },
                timeout=2.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                action_id = data.get("action_id", "unknown")
                return f"Action queued: {action_id}"
            return f"Queue action failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Queue action failed: {exc}"

    def get_action_status(self) -> str:
        try:
            resp = self._http.get("agent/actions/status", timeout=2.0)
            if resp.status_code == 200:
                return str(resp.json())
            return f"Action status failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Action status failed: {exc}"

    def cancel_action(self, action_id: str) -> str:
        try:
            resp = self._http.post(
                "agent/actions/cancel",
                json_data={"action_id": str(action_id)},
                timeout=2.0,
            )
            if resp.status_code == 200:
                return str(resp.json())
            return f"Cancel action failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Cancel action failed: {exc}"

    def express_emotion(
        self,
        emotion: str,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: list[str] | None = None,
        text: str | None = None,
        language: str = "tr",
    ) -> str:
        """Express an emotion across all modalities through the Expression service.
        
        This delegates to the Expression module's /expression/express endpoint,
        which coordinates LEDs, OLED, TTS, head, and ears atomically with
        semantic emotion rendering from the canonical emotion vocabulary.
        """
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            int(min(2.0, max(0.1, float(intensity))))
            dur = min(30.0, max(0.5, float(duration_s)))
            mods = list(modalities) if modalities else ["leds", "oled", "voice", "head"]
            # Fetch render hints from local vocab for an immediate semantic summary
            try:
                from modules.common.emotion_vocab import get_vocab
                render = get_vocab().get_render_dict(emotion)
                canon = render["canonical"]
            except Exception:
                render = None
                canon = str(emotion).strip().lower()
            try:
                resp = self._http.post(
                    "/expression/express",
                    json_data={
                        "emotion": canon,
                        "intensity": round(float(intensity), 3),
                        "duration_s": round(float(dur), 3),
                        "modalities": mods,
                        "text": text,
                        "language": str(language or "tr"),
                    },
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    ok = body.get("ok", False)
                    if not ok:
                        return f"Expression skipped: {body.get('reason', 'unknown')}"
                    return (
                        f"Expressed {canon} (intensity={intensity:.2f}, "
                        f"{duration_s:.1f}s) across {', '.join(mods)}. "
                        f"Render: LED={render['neopixel']['effect']} "
                        f"RGB={render['neopixel']['rgb'] if render else 'n/a'}, "
                        f"OLED={render['oled']['animation'] if render else 'n/a'}, "
                        f"TTS={render['voice']['tone'] if render else 'n/a'}"
                    )
                return f"Expression failed: HTTP {resp.status_code}"
            except Exception as exc:
                return f"Expression failed: {exc}"
        except (TypeError, ValueError) as exc:
            return f"Expression parameter error: {exc}"
