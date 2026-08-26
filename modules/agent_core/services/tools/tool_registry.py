from __future__ import annotations

# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_llm_tool_registry'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime capabilities and execution: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ToolRegistry remains an LLM-facing proposal surface. Physical actions must still pass through action/safety/capability paths.'
# --- End SentryBOT safety/action boundary contract ---


import json
import logging
from typing import Any, Callable, Dict, List, Optional

from .http_client import HttpClient
from .motion_tools import MotionToolsMixin
from .vision_tools import VisionToolsMixin
from .social_tools import SocialToolsMixin
from .hardware_tools import HardwareToolsMixin
from .tool_schemas import get_all_tool_definitions

logger = logging.getLogger("agent.tools")


class ToolRegistry(MotionToolsMixin, VisionToolsMixin, SocialToolsMixin, HardwareToolsMixin):
    """
    Registers Python functions as native tools for the LLM.
    Provides the JSON schemas for Ollama.
    """

    _VLM_TOOL_NAMES: frozenset = frozenset(
        {
            "get_vision",
            "get_visual_context",
            "describe_scene",
            "ask_vlm_about_scene",
            "focus_person",
        }
    )

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

    def _url(self, path: str) -> str:
        return f"{self._gateway_base_url}/{str(path).lstrip('/')}"

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

    def _register_all(self):
        definitions = get_all_tool_definitions()
        for schema in definitions:
            name = schema["function"]["name"]
            if hasattr(self, name):
                func = getattr(self, name)
                self._register(func, schema)

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

    def get_tools(self, include: List[str] | None = None) -> List[Dict[str, Any]]:
        """Compatibility alias for Ollama native tool schemas."""
        return self.get_tool_schema(include=include)

    def get_tool_names(self) -> List[str]:
        return list(self.tools.keys())
