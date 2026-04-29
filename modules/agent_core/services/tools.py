from typing import Dict, Any, Callable, List, Optional
import logging
import json

logger = logging.getLogger("agent.tools")

class ToolRegistry:
    """
    Registers Python functions as native tools for the LLM.
    Provides the JSON schemas for Ollama.
    """
    def __init__(self, client, memory, slam, world_state, safety_filter):
        self.client = client
        self.memory = memory
        self.slam = slam
        self.world_state = world_state
        self.safety = safety_filter
        self.status_hook: Optional[Callable[[Dict[str, Any]], None]] = None
        
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []
        
        self._register_all()

    def _register(self, func: Callable, schema: Dict[str, Any]):
        name = schema["function"]["name"]
        self.tools[name] = func
        self.schemas.append(schema)

    def execute(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Executes the mapped tool and returns the string result."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."
            
        try:
            logger.info(f"LLM called tool: {tool_name}({kwargs})")
            self._emit_status({"type": "tool_start", "tool": tool_name, "args": kwargs})
            result = self.tools[tool_name](**kwargs)
            self._emit_status({"type": "tool_done", "tool": tool_name})
            return json.dumps(result) if isinstance(result, (dict, list)) else str(result)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            self._emit_status({"type": "tool_error", "tool": tool_name, "error": str(e)})
            return f"Error executing {tool_name}: {e}"

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
        return [schema for schema in self.schemas if schema.get("function", {}).get("name") in include_set]

    def get_tool_names(self) -> List[str]:
        return list(self.tools.keys())

    # ==========================================
    # TOOL IMPLEMENTATIONS & SCHEMAS
    # ==========================================

    def _register_all(self):
        self._register(self.move_head, {
            "type": "function",
            "function": {
                "name": "move_head",
                "description": "Move the robot's head to specific pan and tilt angles (0-180). 90 is center.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pan": {"type": "integer", "description": "Horizontal angle (0=Right, 90=Center, 180=Left)"},
                        "tilt": {"type": "integer", "description": "Vertical angle (0=Down, 90=Center, 180=Up)"}
                    },
                    "required": ["pan", "tilt"]
                }
            }
        })

        self._register(self.play_sound, {
            "type": "function",
            "function": {
                "name": "play_sound",
                "description": "Play an audio file from the SD card (e.g., 'alert_1.mp3', 'start.wav').",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Name of the audio file"}},
                    "required": ["name"]
                }
            }
        })

        self._register(self.set_lights, {
            "type": "function",
            "function": {
                "name": "set_lights",
                "description": "Set the Neopixel body lights to a specific effect and color.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "effect": {
                            "type": "string",
                            "enum": ["COMET", "PULSE", "WAVE", "SOLID", "OFF", "BREATHE", "RANDOM_BLINK", "TWINKLE"],
                            "description": "The animation effect"
                        },
                        "color": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "RGB color array like [255, 0, 0] for red"
                        }
                    },
                    "required": ["effect"]
                }
            }
        })

        self._register(self.set_laser, {
            "type": "function",
            "function": {
                "name": "set_laser",
                "description": "Turn the targeting laser on or off.",
                "parameters": {
                    "type": "object",
                    "properties": {"on": {"type": "boolean", "description": "True to turn on, False to turn off"}},
                    "required": ["on"]
                }
            }
        })

        self._register(self.oled_face, {
            "type": "function",
            "function": {
                "name": "oled_face",
                "description": "Change the expression on the OLED eyes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "enum": ["Alert", "Angry", "Bored", "Happy", "Sad", "ScanningEyes", "Winking", "look_up", "normal", "logo", "scan", "blink", "emotive"],
                            "description": "The emotion or animation to display on the eyes"
                        }
                    },
                    "required": ["expression"]
                }
            }
        })

        self._register(self.set_emotion, {
            "type": "function",
            "function": {
                "name": "set_emotion",
                "description": "Set the robot's internal emotional state.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "enum": ["joy", "sadness", "anger", "fear", "trust", "disgust", "anticipation", "surprise", "tired", "neutral"],
                            "description": "The dominant emotion to feel"
                        }
                    },
                    "required": ["emotion"]
                }
            }
        })

        self._register(self.interaction_event, {
            "type": "function",
            "function": {
                "name": "interaction_event",
                "description": "Trigger a pre-programmed complex interaction/animation sequence.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event": {
                            "type": "string",
                            "enum": ["autonomy.excited", "autonomy.bored", "autonomy.monologue", "autonomy.look_around", "autonomy.blink", "autonomy.stretch", "autonomy.sleep", "autonomy.wake"],
                            "description": "The interaction event to emit"
                        }
                    },
                    "required": ["event"]
                }
            }
        })

        self._register(self.search_memory, {
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "Search your episodic database for past events, dialogues, or seen people.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Search keyword"}},
                    "required": ["query"]
                }
            }
        })

        self._register(self.get_vision, {
            "type": "function",
            "function": {
                "name": "get_vision",
                "description": "Look through the camera and return recently detected objects/people.",
                "parameters": {"type": "object", "properties": {}}
            }
        })

        self._register(self.get_sensor_data, {
            "type": "function",
            "function": {
                "name": "get_sensor_data",
                "description": "Get current battery level and ultrasonic distance measurements.",
                "parameters": {"type": "object", "properties": {}}
            }
        })

        self._register(self.get_location, {
            "type": "function",
            "function": {
                "name": "get_location",
                "description": "Get your current topological map location.",
                "parameters": {"type": "object", "properties": {}}
            }
        })

        self._register(self.pathfind, {
            "type": "function",
            "function": {
                "name": "pathfind",
                "description": "Finds a path from your current location to a known room/node.",
                "parameters": {
                    "type": "object",
                    "properties": {"destination": {"type": "string", "description": "Target map node name"}},
                    "required": ["destination"]
                }
            }
        })

        self._register(self.update_location, {
            "type": "function",
            "function": {
                "name": "update_location",
                "description": "Update current location and learn it if it is a new place.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Current location name"},
                    },
                    "required": ["location"],
                },
            },
        })

        self._register(self.connect_locations, {
            "type": "function",
            "function": {
                "name": "connect_locations",
                "description": "Connect two map locations and learn unknown nodes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source location"},
                        "destination": {"type": "string", "description": "Destination location"},
                    },
                    "required": ["source", "destination"],
                },
            },
        })

        self._register(self.list_locations, {
            "type": "function",
            "function": {
                "name": "list_locations",
                "description": "List all known map locations.",
                "parameters": {"type": "object", "properties": {}},
            },
        })

    # ==========================================
    # TOOL LOGIC
    # ==========================================

    def move_head(self, pan: int, tilt: int) -> str:
        if not self.client: return "Error: Hardware client disconnected."
        safe_pan = self.safety.clamp_servo(pan)
        safe_tilt = self.safety.clamp_servo(tilt)
        resp = self.client.move_head(safe_pan, safe_tilt)
        return f"Head moved to pan={safe_pan}, tilt={safe_tilt}. Hardware response: {resp}"

    def play_sound(self, name: str) -> str:
        if not self.client: return "Error: Hardware client disconnected."
        resp = self.client.play_sound(name)
        return f"Playing sound: {name}. Response: {resp}"

    def set_lights(self, effect: str, color: List[int] = None) -> str:
        if not self.client: return "Error: Hardware client disconnected."
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
        if not self.client: return "Error: Hardware client disconnected."
        resp = self.client.set_laser(on=on)
        return f"Laser turned {'ON' if on else 'OFF'}. Response: {resp}"

    def oled_face(self, expression: str) -> str:
        if not self.client: return "Error: Hardware client disconnected."
        anim_list = ["ScanningEyes", "Winking", "scan", "blink", "emotive"]
        if expression in anim_list:
            resp = self.client.oled_anim(expression)
        else:
            resp = self.client.oled_show(expression)
        return f"OLED face updated to {expression}. Response: {resp}"

    def set_emotion(self, emotion: str) -> str:
        if not self.client: return "Error: Hardware client disconnected."
        self.client.update_emotions([emotion])
        return f"Internal emotion set to: {emotion}"

    def interaction_event(self, event: str) -> str:
        if not self.client: return "Error: Hardware client disconnected."
        self.client.push_interaction_event(event)
        return f"Triggered complex interaction event: {event}"

    def search_memory(self, query: str) -> str:
        res = self.memory.search_memory(query, limit=5)
        if not res:
            return "No matching memories found."
        return str(res)

    def get_vision(self) -> str:
        if not self.client: return "Error: Vision client disconnected."
        results = self.client.get_latest_vision_results(limit=5)
        if not results:
            return "Vision results unavailable. Continue with text-only reasoning if needed."
        return f"Camera sees: {results}"

    def get_sensor_data(self) -> str:
        bat = self.world_state.get_state().get("battery_percent", "unknown")
        dist_info = "Distance unknown"
        if self.client:
            ultra = self.client.read_sensor("ultra_read")
            if ultra and "cm" in str(ultra): # Example check, actual parsing may vary
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
