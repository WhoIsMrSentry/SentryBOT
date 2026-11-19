from __future__ import annotations

# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = "agent_core_compat_llm_tool_registry"
SAFETY_ACTION_RUNTIME_OWNER = "robot-runtime capabilities and execution: modules.autonomy"
SAFETY_ACTION_BOUNDARY_REASON = "ToolRegistry remains an LLM-facing proposal surface. Physical actions must still pass through action/safety/capability paths."
# --- End SentryBOT safety/action boundary contract ---

import inspect
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .hardware_tools import HardwareToolsMixin
from .http_client import HttpClient
from .motion_tools import MotionToolsMixin
from .persona_tools import PersonaToolsMixin
from .social_tools import SocialToolsMixin
from .tool_schemas import get_all_tool_definitions
from .vision_tools import VisionToolsMixin
from .web_tools import WebToolsMixin

logger = logging.getLogger("agent.tools")


def _validate_param_type(val: Any, expected: str, arg_name: str) -> None:
    kind = str(expected or "string").strip().lower()
    if kind == "string" and not isinstance(val, str):
        raise ValueError(f"argument '{arg_name}' must be string")
    elif kind == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
        raise ValueError(f"argument '{arg_name}' must be integer")
    elif kind == "number" and (isinstance(val, bool) or not isinstance(val, (int, float))):
        raise ValueError(f"argument '{arg_name}' must be number")
    elif kind == "boolean" and not isinstance(val, bool):
        raise ValueError(f"argument '{arg_name}' must be boolean")
    elif kind == "object" and not isinstance(val, dict):
        raise ValueError(f"argument '{arg_name}' must be object")
    elif kind == "array" and not isinstance(val, list):
        raise ValueError(f"argument '{arg_name}' must be array")


class ToolRegistry(MotionToolsMixin, VisionToolsMixin, SocialToolsMixin, HardwareToolsMixin, WebToolsMixin, PersonaToolsMixin):
    """
    Registers Python functions as native tools for the LLM.
    Provides JSON schemas for Ollama, validates tool arguments, and bridges connected MCP tools.
    """

    _VLM_TOOL_NAMES: frozenset = frozenset(
        {
            "get_vision",
            "get_visual_context",
            "describe_scene",
            "ask_vlm_about_scene",
            "focus_person",
            "read_text_ocr",
            "register_face",
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
        action_arbiter=None,
        expression_arbiter=None,
        mcp_client=None,
        localize_speech_fn: Optional[Callable[[str, str], Tuple[str, str]]] = None,
        persona_manager: Any = None,
        apply_persona_fn: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ):
        self.client = client
        self.memory = memory
        self.slam = slam
        self.world_state = world_state
        self.safety = safety_filter
        self.tool_execution_arbiter = tool_execution_arbiter
        self.vision_arbiter = vision_arbiter
        self.action_arbiter = action_arbiter
        self.expression_arbiter = expression_arbiter
        self.mcp_client = mcp_client
        self.localize_speech_fn = localize_speech_fn
        self.persona_manager = persona_manager
        self.apply_persona_fn = apply_persona_fn
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
        self._schema_by_name: Dict[str, Dict[str, Any]] = {}
        self._mcp_targets: Dict[str, Tuple[str, str]] = {}
        self._metrics_lock = threading.Lock()
        self._tool_metrics: Dict[str, Dict[str, int]] = {}

        self._register_all()

    def attach_mcp_client(self, mcp_client: Any) -> None:
        self.mcp_client = mcp_client

    def close(self) -> None:
        self._http.close()

    def _record_metric(self, tool_name: str, *, ok: bool, timed_out: bool = False) -> None:
        with self._metrics_lock:
            bucket = self._tool_metrics.setdefault(
                tool_name,
                {"calls": 0, "errors": 0, "timeouts": 0},
            )
            bucket["calls"] += 1
            if timed_out:
                bucket["timeouts"] += 1
            if not ok:
                bucket["errors"] += 1

    def metrics(self) -> Dict[str, Dict[str, int]]:
        with self._metrics_lock:
            return {name: dict(counts) for name, counts in self._tool_metrics.items()}

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
        self._schema_by_name[name] = schema

    def _register_all(self):
        definitions = get_all_tool_definitions()
        for schema in definitions:
            name = schema["function"]["name"]
            if hasattr(self, name):
                func = getattr(self, name)
                self._register(func, schema)

    @staticmethod
    def _filter_by_signature(func: Optional[Callable], args: Dict[str, Any]) -> Dict[str, Any]:
        if func is None:
            return args
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return args
        params = sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return args
        allowed = {
            name
            for name, p in params.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return {k: v for k, v in args.items() if k in allowed}

    def _validate_and_filter_args(
        self,
        tool_name: str,
        func: Optional[Callable],
        schema: Optional[Dict[str, Any]],
        raw_kwargs: Any,
    ) -> Dict[str, Any]:
        if raw_kwargs is None:
            raw_dict: Dict[str, Any] = {}
        elif isinstance(raw_kwargs, Mapping):
            raw_dict = dict(raw_kwargs)
        else:
            raise ValueError("arguments must be an object")

        if not isinstance(schema, dict):
            return self._filter_by_signature(func, raw_dict)

        fn_spec = schema.get("function") if isinstance(schema.get("function"), dict) else {}
        params = fn_spec.get("parameters") if isinstance(fn_spec.get("parameters"), dict) else {}
        props = params.get("properties") if isinstance(params.get("properties"), dict) else {}
        required = params.get("required") if isinstance(params.get("required"), list) else []

        for req_name in required:
            if req_name not in raw_dict or raw_dict[req_name] is None:
                raise ValueError(f"missing required argument '{req_name}'")

        filtered: Dict[str, Any] = {}
        dropped: List[str] = []
        for k, v in raw_dict.items():
            if k not in props:
                dropped.append(str(k))
                continue
            if v is not None:
                prop_spec = props[k] if isinstance(props[k], dict) else {}
                if prop_spec.get("type"):
                    _validate_param_type(v, str(prop_spec["type"]), str(k))
                allowed_enum = prop_spec.get("enum")
                if isinstance(allowed_enum, list) and allowed_enum and v not in allowed_enum:
                    raise ValueError(f"argument '{k}' must be one of {allowed_enum}")
            filtered[k] = v

        if dropped:
            logger.debug("Filtered unexpected kwargs for %s: %s", tool_name, dropped)
        return self._filter_by_signature(func, filtered)

    def _collect_mcp_tools(self) -> Dict[str, Tuple[str, str, Dict[str, Any]]]:
        mc = getattr(self, "mcp_client", None)
        if mc is None or not getattr(mc, "enabled", True):
            return {}

        collected: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}
        conns_raw = getattr(mc, "_conns", None)
        per_server: List[Tuple[str, List[Dict[str, Any]]]] = []
        if isinstance(conns_raw, dict):
            lock = getattr(mc, "_lock", None)
            if lock is not None:
                with lock:
                    items = list(conns_raw.items())
            else:
                items = list(conns_raw.items())
            for srv, conn in items:
                if conn is None or not getattr(conn, "alive", True):
                    continue
                t_list = getattr(conn, "tools_cache", None)
                if not t_list and hasattr(conn, "tools"):
                    try:
                        t_list = conn.tools(refresh=False)
                    except Exception:
                        t_list = []
                per_server.append((str(srv), list(t_list or [])))
        elif hasattr(mc, "tools"):
            try:
                res = mc.tools()
                if isinstance(res, dict) and isinstance(res.get("servers"), dict):
                    for srv, t_list in res["servers"].items():
                        per_server.append((str(srv), list(t_list or [])))
            except Exception:
                pass

        for srv, t_list in per_server:
            for item in t_list:
                if not isinstance(item, dict):
                    continue
                t_name = str(item.get("name", "")).strip()
                if not t_name:
                    continue
                qual_name = f"mcp__{srv}__{t_name}"
                input_schema = item.get("inputSchema")
                if not isinstance(input_schema, dict):
                    input_schema = {"type": "object", "properties": {}, "required": []}
                schema = {
                    "type": "function",
                    "function": {
                        "name": qual_name,
                        "description": f"[MCP:{srv}] {item.get('description', '')}".strip(),
                        "parameters": input_schema,
                    },
                }
                collected[qual_name] = (srv, t_name, schema)
        self._mcp_targets = {q: (srv, t) for q, (srv, t, _) in collected.items()}
        return collected

    def list_mcp_tool_definitions(self, include: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        collected = self._collect_mcp_tools()
        if not collected:
            return []
        if not include:
            return [entry[2] for entry in collected.values()]
        inc = {str(x).strip() for x in include if str(x).strip()}
        if "mcp:*" in inc:
            return [entry[2] for entry in collected.values()]
        out: List[Dict[str, Any]] = []
        for qual_name, (srv, raw_name, schema) in collected.items():
            if qual_name in inc or raw_name in inc or f"mcp:{srv}" in inc:
                out.append(schema)
        return out

    @staticmethod
    def _looks_like_timeout(text: str, exc: Optional[Exception] = None) -> bool:
        if exc is not None and (
            isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
        ):
            return True
        lowered = str(text or "").lower()
        return any(tok in lowered for tok in ("timeout", "timed out", "gecikti"))

    def _execute_mcp_tool(self, tool_name: str, raw_kwargs: Any, schema: Dict[str, Any]) -> str:
        srv, raw_name = self._mcp_targets[tool_name]
        try:
            args = self._validate_and_filter_args(tool_name, None, schema, raw_kwargs)
            res = self.mcp_client.call(srv, raw_name, args)
            is_err = bool(res.get("is_error", False)) if isinstance(res, dict) else False
            text = str(res.get("text", "ok")) if isinstance(res, dict) else str(res)
            timed_out = is_err and self._looks_like_timeout(text)
            self._record_metric(tool_name, ok=not is_err, timed_out=timed_out)
            if is_err:
                self._emit_status({"type": "tool_error", "tool": tool_name, "error": text})
                return f"Error executing {tool_name}: {text}"
            self._emit_status({"type": "tool_done", "tool": tool_name, "result": text})
            return text
        except Exception as exc:
            timed_out = self._looks_like_timeout(str(exc), exc)
            self._record_metric(tool_name, ok=False, timed_out=timed_out)
            self._emit_status({"type": "tool_error", "tool": tool_name, "error": str(exc)})
            return f"Error executing {tool_name}: {exc}"

    def execute(self, tool_name: str, kwargs: Dict[str, Any], laya_hint: Optional[str] = None) -> str:
        """Executes the LLM-selected tool; Laya hint is diagnostic only, never authority."""
        if tool_name not in self.tools:
            mcp_map = self._collect_mcp_tools()
            if tool_name in mcp_map:
                return self._execute_mcp_tool(tool_name, kwargs, mcp_map[tool_name][2])
            self._record_metric(str(tool_name), ok=False, timed_out=False)
            return f"Error: Tool '{tool_name}' not found."

        hint = str(laya_hint or "").strip()[:64]
        acquired = False
        vision_held = False
        try:
            func = self.tools[tool_name]
            validated_kwargs = self._validate_and_filter_args(
                tool_name,
                func,
                self._schema_by_name.get(tool_name),
                kwargs,
            )
            if self.tool_execution_arbiter is not None:
                if not self.tool_execution_arbiter.acquire(tool_name):
                    self._record_metric(tool_name, ok=False, timed_out=False)
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
                self._record_metric(tool_name, ok=False, timed_out=False)
                self._emit_status(
                    {
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": "camera_unavailable",
                    }
                )
                return self._vision_unavailable_message()
            if not self._acquire_vision(tool_name):
                self._record_metric(tool_name, ok=False, timed_out=False)
                self._emit_status(
                    {
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": "vision_busy",
                    }
                )
                return f"Error executing {tool_name}: vision arbiter busy"
            vision_held = tool_name in self._VLM_TOOL_NAMES
            logger.info("LLM called tool: %s(%s)", tool_name, validated_kwargs)
            result = func(**validated_kwargs)
            result_str = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
            timed_out = self._looks_like_timeout(result_str)
            failed = result_str.lower().startswith("error") or timed_out
            self._record_metric(tool_name, ok=not failed, timed_out=timed_out)
            self._emit_status(
                {
                    "type": "tool_done",
                    "tool": tool_name,
                    "result": result_str,
                    **({"laya_hint": hint, "laya_hint_matches": hint == tool_name} if hint else {}),
                }
            )
            return result_str
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            timed_out = self._looks_like_timeout(str(e), e)
            self._record_metric(tool_name, ok=False, timed_out=timed_out)
            self._emit_status({"type": "tool_error", "tool": tool_name, "error": str(e)})
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

    def get_tool_schema(
        self,
        include: List[str] | None = None,
        *,
        include_mcp: bool = True,
    ) -> List[Dict[str, Any]]:
        """Returns all tool schemas (plus connected MCP tools) or a filtered subset."""
        if not include:
            base = list(self.schemas)
        else:
            include_set = {str(name) for name in include if str(name) in self.tools}
            base = [
                schema
                for schema in self.schemas
                if schema.get("function", {}).get("name") in include_set
            ]
        if include_mcp and self.mcp_client is not None:
            base.extend(self.list_mcp_tool_definitions(include=include))
        return base

    def get_tools(
        self,
        include: List[str] | None = None,
        *,
        include_mcp: bool = True,
    ) -> List[Dict[str, Any]]:
        """Compatibility alias for Ollama native tool schemas."""
        return self.get_tool_schema(include=include, include_mcp=include_mcp)

    def get_tool_names(self) -> List[str]:
        names = list(self.tools.keys())
        for qual_name in self._collect_mcp_tools():
            if qual_name not in names:
                names.append(qual_name)
        return names
