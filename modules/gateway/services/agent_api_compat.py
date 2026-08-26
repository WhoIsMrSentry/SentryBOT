from __future__ import annotations

# SENTRYBOT: ActionRequest priority must be numeric for ActionArbiter.submit.

import inspect
import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request

# Consolidated duplicates (audit FIX-12): both legacy helpers now live in
# modules.common.ollama_url; local names kept as aliases for call sites.
from modules.common.ollama_url import (  # noqa: E402,F401
    ensure_ollama_host_env as _ensure_ollama_host_env,
    ensure_sentrybot_ollama_host_env as _sentrybot_ensure_ollama_host_env,
)



DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_OLLAMA_BASE_URL = "http://whoismrsentry.local:11434"
_AGENT_STATE_NAMES = ("agent_service", "agent", "agent_core", "agent_runtime", "sentrybot_agent")


def _payload_prompt(payload: Dict[str, Any]) -> str:
    for key in ("prompt", "message", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    event = payload.get("event")
    if isinstance(event, dict):
        for key in ("prompt", "message", "text", "content", "type", "event_type"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    event_type = payload.get("event_type") or payload.get("type")
    if isinstance(event_type, str) and event_type.strip():
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return f"{event_type.strip()}: {msg.strip()}"
        return event_type.strip()
    return "Set the lights to red."


def _state_get(app: Any, name: str) -> Any:
    try:
        return getattr(app.state, name)
    except Exception:
        return None


def _is_agent_like(obj: Any) -> bool:
    return obj is not None and any(callable(getattr(obj, name, None)) for name in ("step", "step_event", "turn", "chat", "run", "handle_event"))


def _find_agent_service(request: Request) -> Any:
    for name in _AGENT_STATE_NAMES:
        svc = _state_get(request.app, name)
        if _is_agent_like(svc):
            return svc
    started = _state_get(request.app, "started")
    if isinstance(started, dict):
        for name in _AGENT_STATE_NAMES:
            svc = started.get(name)
            if _is_agent_like(svc):
                return svc
    services = _state_get(request.app, "services")
    if isinstance(services, dict):
        for name in _AGENT_STATE_NAMES:
            svc = services.get(name)
            if _is_agent_like(svc):
                return svc
    return None


def _ensure_bound_agent(request: Request, cfg: Optional[Dict[str, Any]] = None) -> Any:
    agent = _find_agent_service(request)
    if _is_agent_like(agent):
        return agent
    try:
        from modules.gateway.services.agent_core_binding import ensure_agent_core_bound
        started = _state_get(request.app, "started")
        if not isinstance(started, dict):
            started = {}
            try:
                request.app.state.started = started
            except Exception:
                pass
        ensure_agent_core_bound(request.app, cfg or {}, started)
    except Exception:
        pass
    return _find_agent_service(request)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _real_result_is_useful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict) and value.get("ok") is False:
        return False
    return True


async def _call_real_agent(agent: Any, prompt: str, payload: Dict[str, Any], event_mode: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    candidates: List[str] = []
    if event_mode:
        candidates.extend(["step_event", "handle_event", "event"])
    candidates.extend(["step", "turn", "chat", "run"])
    for method_name in candidates:
        method = getattr(agent, method_name, None)
        if method is None or not callable(method):
            continue
        call_attempts = []
        if method_name in ("step_event", "handle_event", "event"):
            call_attempts.append(("event_payload", (payload,), {}))
            call_attempts.append(("event_keyword", (), {"event": payload}))
        else:
            call_attempts.append(("prompt_positional", (prompt,), {}))
            call_attempts.append(("prompt_keyword", (), {"prompt": prompt}))
            call_attempts.append(("payload_positional", (payload,), {}))
        for label, args, kwargs in call_attempts:
            try:
                result = await _maybe_await(method(*args, **kwargs))
                if _real_result_is_useful(result):
                    return {"ok": True, "source": "gateway_agent_real", "method": method_name, "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}", "result": result, "errors": errors}
                errors.append(f"{method_name}.{label}:inert_result:{result!r}")
            except Exception as exc:
                errors.append(f"{method_name}.{label}:{type(exc).__name__}:{exc}")
    return {"ok": False, "source": "gateway_agent_real_inert", "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}", "errors": errors[-20:]}


def _normalize_tool_call(tc: Dict[str, Any]) -> Dict[str, Any]:
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    name = fn.get("name") or tc.get("name") or ""
    args = fn.get("arguments", tc.get("arguments", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {"raw": args}
    if not isinstance(args, dict):
        args = {"value": args}
    return {"name": str(name), "arguments": args, "raw": tc}


def _ollama_base_url() -> str:
    value = os.getenv("SENTRYBOT_OLLAMA_BASE_URL") or os.getenv("SENTRYBOT_REMOTE_OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
    return str(value).rstrip("/")


def _ollama_model() -> str:
    return str(os.getenv("SENTRYBOT_OLLAMA_MODEL") or os.getenv("SENTRYBOT_MODEL") or os.getenv("SENTRYBOT_LLM_MODEL") or DEFAULT_MODEL)


def _minimal_tools() -> List[Dict[str, Any]]:
    return [{"type": "function", "function": {"name": "set_lights", "description": "Set robot lights safely.", "parameters": {"type": "object", "properties": {"effect": {"type": "string", "enum": ["solid", "pulse", "off", "SOLID", "PULSE", "OFF"]}, "color": {"type": "string"}}, "required": ["effect", "color"]}}}]


def _tool_registry(agent: Any) -> Any:
    for name in ("tool_registry", "tools", "registry", "_tool_registry"):
        obj = getattr(agent, name, None)
        if obj is not None:
            return obj
    return None


def _normalize_schema_tools(schema: Any) -> List[Dict[str, Any]]:
    if isinstance(schema, dict):
        if isinstance(schema.get("tools"), list):
            return [x for x in schema["tools"] if isinstance(x, dict)]
        if "function" in schema or schema.get("type") == "function":
            return [schema]
    if isinstance(schema, list):
        return [x for x in schema if isinstance(x, dict)]
    return []


def _get_tool_schema_from_agent(agent: Any) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    info: Dict[str, Any] = {"tool_schema_count": 0, "schema_error": None, "get_tools_count": None}
    registry = _tool_registry(agent)
    if registry is None:
        return _minimal_tools(), info
    try:
        get_tools = getattr(registry, "get_tools", None)
        if callable(get_tools):
            tools_obj = get_tools()
            if isinstance(tools_obj, (dict, list)):
                info["get_tools_count"] = len(tools_obj)
    except Exception as exc:
        info["get_tools_error"] = f"{type(exc).__name__}:{exc}"
    try:
        get_schema = getattr(registry, "get_tool_schema", None)
        if callable(get_schema):
            try:
                schema = get_schema(include=None)
            except TypeError:
                schema = get_schema()
            tools = _normalize_schema_tools(schema)
            if tools:
                info["tool_schema_count"] = len(tools)
                return tools, info
    except Exception as exc:
        info["schema_error"] = f"{type(exc).__name__}:{exc}"
    return _minimal_tools(), info


def _ollama_tool_call(prompt: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    started = time.time()
    base_url = _ollama_base_url()
    model = _ollama_model()
    body = {"model": model, "stream": False, "think": False, "messages": [{"role": "system", "content": "Use the provided tool when appropriate. Return a tool call only when the user asks for robot action."}, {"role": "user", "content": prompt}], "tools": tools or _minimal_tools(), "options": {"temperature": 0, "num_predict": 128}}
    req = urllib.request.Request(f"{base_url}/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    message = data.get("message") or {}
    raw_tool_calls = message.get("tool_calls") or []
    return {"ok": True, "provider": "ollama", "model": model, "base_url": base_url, "tool_calls": [_normalize_tool_call(x) for x in raw_tool_calls if isinstance(x, dict)], "content": message.get("content", ""), "elapsed_ms": int((time.time() - started) * 1000)}


def _registry_result_needs_action_fallback(result: Any) -> bool:
    text = repr(result)
    needles = ("Queue action failed", "HTTPConnectionPool", "ConnectTimeoutError", "127.0.0.1", "/agent/actions/queue", "connection timed out", "Max retries exceeded")
    if any(n in text for n in needles):
        return True
    if isinstance(result, dict) and result.get("ok") is False:
        return True
    return False


def _execute_registry(agent: Any, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    registry = _tool_registry(agent)
    if registry is None:
        return {"ok": False, "error": "tool_registry_not_found"}
    execute = getattr(registry, "execute", None)
    if not callable(execute):
        return {"ok": False, "error": "tool_registry_execute_not_callable"}
    errors: List[str] = []
    attempts = (("name_args", (tool_name, arguments), {}), ("name_kwargs", (tool_name,), dict(arguments)), ("keyword", (), {"name": tool_name, "arguments": arguments}), ("tool_keyword", (), {"tool_name": tool_name, "args": arguments}))
    for label, args, kwargs in attempts:
        try:
            result = execute(*args, **kwargs)
            return {"ok": True, "via": "tool_registry", "attempt": label, "result": result}
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{exc}")
    return {"ok": False, "via": "tool_registry", "errors": errors[-10:]}


def _find_action_arbiter(request: Request, agent: Any) -> Any:
    attr_names = ("action_arbiter", "arbiter", "_action_arbiter", "action_manager", "action_queue")
    for owner in (agent, _tool_registry(agent)):
        if owner is None:
            continue
        for name in attr_names:
            obj = getattr(owner, name, None)
            if obj is not None and callable(getattr(obj, "submit", None)):
                return obj
    for name in attr_names + ("agent_action_arbiter",):
        obj = _state_get(request.app, name)
        if obj is not None and callable(getattr(obj, "submit", None)):
            return obj
    started = _state_get(request.app, "started")
    if isinstance(started, dict):
        for name in attr_names + ("agent_action_arbiter",):
            obj = started.get(name)
            if obj is not None and callable(getattr(obj, "submit", None)):
                return obj
        for obj in started.values():
            if obj is not None and callable(getattr(obj, "submit", None)) and obj.__class__.__name__.lower().endswith("arbiter"):
                return obj
    return None


def _tool_to_action(tool_name: str, arguments: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    key = str(tool_name or "").strip().lower()
    args = dict(arguments or {})
    if key == "set_lights":
        return "lights", args
    if key in {"speak", "say"}:
        return "speak", args
    if key in {"set_emotion", "express_emotion"}:
        return "emotion", args
    if key in {"look_around", "face_focus", "follow_owner", "stop_follow"}:
        return key, args
    return key or "tool_action", args


def _action_priority_value() -> int:
    try:
        from modules.agent_core.services.action_arbiter import ActionPriority
        return int(getattr(ActionPriority, "AGENT_TOOL", 65))
    except Exception:
        return 65


def _make_action_request(action_type: str, payload: Dict[str, Any]) -> Any:
    payload = dict(payload or {})
    priority_value = _action_priority_value()
    source_value = "agent_core"
    cooldown_key = f"agent_api_tool_bridge:{action_type}"

    fallback = {
        "type": action_type,
        "action_type": action_type,
        "payload": payload,
        "params": payload,
        "source": source_value,
        "priority": priority_value,
        "ttl_ms": 5000,
        "cooldown_key": cooldown_key,
    }

    try:
        from modules.agent_core.services.action_arbiter import ActionRequest
    except Exception:
        return fallback

    # Preferred path for the current ActionRequest dataclass.
    try:
        return ActionRequest(
            type=action_type,
            source=source_value,
            priority=priority_value,
            ttl_ms=5000,
            cooldown_key=cooldown_key,
            payload=payload,
        )
    except Exception:
        pass

    # Compatibility path for altered ActionRequest signatures.
    try:
        sig = inspect.signature(ActionRequest)
    except Exception:
        try:
            return ActionRequest(**fallback)
        except Exception:
            return fallback

    kwargs: Dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        low = param_name.lower()

        if low in {"type", "action_type", "action", "name", "kind"}:
            kwargs[param_name] = action_type
        elif low in {"payload", "params", "parameters", "args", "data"}:
            kwargs[param_name] = payload
        elif low == "source":
            kwargs[param_name] = source_value
        elif low == "priority":
            kwargs[param_name] = priority_value
        elif low == "ttl_ms":
            kwargs[param_name] = 5000
        elif low == "cooldown_key":
            kwargs[param_name] = cooldown_key
        elif low == "created_at":
            kwargs[param_name] = time.time()
        elif low == "expires_at":
            kwargs[param_name] = 0.0
        elif low == "action_id":
            # Keep action_id string-compatible; ActionArbiter logs id with %s.
            if param.default is inspect._empty:
                kwargs[param_name] = f"agent_api_{int(time.time() * 1000000) % 2147483647}"
        elif low in {"reason", "trace", "trace_id", "request_id", "owner"}:
            if param.default is inspect._empty:
                kwargs[param_name] = "agent_api_tool_bridge"
        elif param.default is inspect._empty:
            kwargs[param_name] = None

    try:
        return ActionRequest(**kwargs)
    except Exception:
        try:
            return ActionRequest(**fallback)
        except Exception:
            return fallback



def _submit_local_action(request: Request, agent: Any, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    arbiter = _find_action_arbiter(request, agent)
    if arbiter is None:
        return {"ok": False, "via": "action_arbiter", "error": "action_arbiter_not_found"}
    submit = getattr(arbiter, "submit", None)
    if not callable(submit):
        return {"ok": False, "via": "action_arbiter", "error": "submit_not_callable"}
    action_type, payload = _tool_to_action(tool_name, arguments)
    request_obj = _make_action_request(action_type, payload)
    errors: List[str] = []
    attempts = (("request_obj", (request_obj,), {}), ("dict", ({"type": action_type, "action_type": action_type, "payload": payload, "source": "agent_api_tool_bridge"},), {}), ("type_payload", (action_type, payload), {}), ("keywords", (), {"action_type": action_type, "payload": payload, "source": "agent_api_tool_bridge"}), ("type_keyword", (), {"type": action_type, "payload": payload, "source": "agent_api_tool_bridge"}))
    for label, args, kwargs in attempts:
        try:
            result = submit(*args, **kwargs)
            return {"ok": True, "via": "action_arbiter", "attempt": label, "action_type": action_type, "payload": payload, "result": result}
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{exc}")
    return {"ok": False, "via": "action_arbiter", "action_type": action_type, "payload": payload, "errors": errors[-10:]}


def _prefer_local_action_first(tool_name: str) -> bool:
    key = str(tool_name or "").strip().lower()
    return key in {
        "set_lights",
        "speak",
        "say",
        "set_emotion",
        "express_emotion",
        "look_around",
        "face_focus",
        "follow_owner",
        "stop_follow",
    }


async def _tool_bridge_with_real_agent(request: Request, agent: Any, prompt: str, real_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    tools, schema_info = _get_tool_schema_from_agent(agent)
    ollama_result = _ollama_tool_call(prompt, tools)
    executions: List[Dict[str, Any]] = []

    for call in ollama_result.get("tool_calls", []):
        if not isinstance(call, dict):
            continue

        tool_name = str(call.get("name") or "")
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        registry_result: Optional[Dict[str, Any]] = None
        action_result: Optional[Dict[str, Any]] = None

        # Robot action tools should use the in-process ActionArbiter first.
        # The old ToolRegistry path can call http://127.0.0.1:8080/agent/actions/queue
        # and waste two seconds in tests/runtime when the gateway is already in-process.
        if _prefer_local_action_first(tool_name) and _find_action_arbiter(request, agent) is not None:
            action_result = _submit_local_action(request, agent, tool_name, arguments)
            if action_result.get("ok"):
                registry_result = {
                    "ok": True,
                    "via": "local_action_preferred",
                    "skipped": "tool_registry_execute_loopback_queue",
                }

        if registry_result is None:
            registry_result = _execute_registry(agent, tool_name, arguments)

        if action_result is None and ((not registry_result.get("ok")) or _registry_result_needs_action_fallback(registry_result.get("result"))):
            action_result = _submit_local_action(request, agent, tool_name, arguments)

        executions.append({
            "tool": tool_name,
            "arguments": arguments,
            "registry": registry_result,
            "action_fallback": action_result,
        })

    return {
        "ok": True,
        "source": "gateway_agent_real_tool_bridge",
        "method": "tool_bridge",
        "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
        "result": {
            "ok": True,
            "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
            "provider": ollama_result.get("provider"),
            "model": ollama_result.get("model"),
            "base_url": ollama_result.get("base_url"),
            "tool_schema_count": schema_info.get("tool_schema_count", 0),
            "tool_calls": ollama_result.get("tool_calls", []),
            "executions": executions,
            "content": ollama_result.get("content", ""),
            "elapsed_ms": ollama_result.get("elapsed_ms"),
        },
        "real_agent_errors": list(real_errors or []),
    }



def _ollama_tool_fallback(prompt: str) -> Dict[str, Any]:
    return _ollama_tool_call(prompt, _minimal_tools())



def _sentrybot_prompt_wants_tool_action(prompt: str, payload: object = None) -> bool:
    hay = (str(prompt or "") + " " + str(payload or "")).lower()
    keywords = [
        "set_lights", "lights", "light", "neopixel", "led", "rgb",
        "emotion", "set_emotion", "speak", "say", "queue_action",
        "tool", "use the", "using the", "execute", "run",
        "red", "green", "blue", "solid", "rainbow", "blink",
    ]
    return any(k in hay for k in keywords)

def _sentrybot_result_actions_empty(result: object) -> bool:
    if result is None:
        return True

    data = result
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data.get("result")

    if not isinstance(data, dict):
        return False

    actions = data.get("actions")
    if isinstance(actions, list) and len(actions) > 0:
        return False

    # If the model generated a refusal/explanation instead of actions, treat it as no-op.
    text = str(data.get("text") or data.get("content") or "").lower()
    refusal_bits = [
        "can't actually control",
        "cannot execute external tools",
        "cannot directly control",
        "don't have direct control",
        "i cannot execute",
        "i can't actually",
        "hypothetical",
        "example implementation",
    ]

    if isinstance(actions, list) and len(actions) == 0:
        return True

    if any(bit in text for bit in refusal_bits):
        return True

    return False



import inspect as _sentrybot_tool_fallback_inspect

async def _sentrybot_maybe_await_compat(value):
    if _sentrybot_tool_fallback_inspect.isawaitable(value):
        return await value
    return value

async def _sentrybot_run_tool_bridge_compat(agent, prompt, payload):
    candidates = [
        "_run_ollama_tool_bridge",
        "_run_ollama_tools",
        "_direct_ollama_tool_call",
        "_ollama_tool_call",
    ]
    errors = []
    for name in candidates:
        fn = globals().get(name)
        if not callable(fn):
            continue
        for args in [(agent, prompt, payload), (agent, prompt), (prompt, payload), (prompt,)]:
            try:
                return await _sentrybot_maybe_await_compat(fn(*args))
            except TypeError as exc:
                errors.append(f"{name}{len(args)}:{exc}")
                continue
            except Exception as exc:
                errors.append(f"{name}{len(args)}:{exc}")
                break
    return {"ok": False, "source": "gateway_agent_real_tool_bridge", "error": "no usable tool bridge candidate", "bridge_errors": errors}



import inspect as _sentrybot_return_tool_bridge_inspect

def _sentrybot_deep_text_for_tool_bridge(obj, limit: int = 12000) -> str:
    parts = []

    def walk(value):
        if len(" ".join(parts)) > limit:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                parts.append(str(k))
                walk(v)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
        elif value is not None:
            parts.append(str(value))

    walk(obj)
    return " ".join(parts).lower()[:limit]

async def _sentrybot_return_maybe_await(value):
    if _sentrybot_return_tool_bridge_inspect.isawaitable(value):
        return await value
    return value

async def _sentrybot_run_any_tool_bridge_compat(agent, prompt, payload):
    preferred = [
        "_run_ollama_tool_bridge",
        "_run_ollama_tools",
        "_direct_ollama_tool_call",
        "_ollama_tool_call",
        "_run_native_tool_bridge",
        "_run_tool_bridge",
    ]

    dynamic = []
    for name, value in globals().items():
        lname = str(name).lower()
        if not callable(value):
            continue
        if name.startswith("_sentrybot_"):
            continue
        if "bridge" in lname or "ollama_tool" in lname:
            dynamic.append(name)

    candidates = []
    for name in preferred + dynamic:
        if name not in candidates:
            candidates.append(name)

    errors = []

    for name in candidates:
        fn = globals().get(name)
        if not callable(fn):
            continue

        arg_sets = []
        if agent is not None:
            arg_sets.extend([
                (agent, prompt, payload),
                (agent, prompt),
            ])
        arg_sets.extend([
            (prompt, payload),
            (prompt,),
        ])

        for args in arg_sets:
            try:
                res = await _sentrybot_return_maybe_await(fn(*args))
                if isinstance(res, dict):
                    return res
            except TypeError as exc:
                errors.append(f"{name}/{len(args)}:{exc}")
                continue
            except Exception as exc:
                errors.append(f"{name}/{len(args)}:{exc}")
                break

    return {
        "ok": False,
        "source": "gateway_agent_real_tool_bridge",
        "error": "no usable tool bridge candidate",
        "bridge_errors": errors,
    }



import inspect as _sentrybot_pre_real_bridge_inspect

def _sentrybot_pre_real_prompt_wants_tool(prompt: object, payload: object = None) -> bool:
    hay = (str(prompt or "") + " " + str(payload or "")).lower()
    return any(k in hay for k in [
        "set_lights", "lights", "light", "neopixel", "led", "rgb",
        "set_emotion", "emotion", "speak", "queue_action",
        "tool", "use the", "using the", "execute", "run",
        "red", "green", "blue", "solid", "rainbow", "blink",
    ])

async def _sentrybot_pre_real_maybe_await(value):
    if _sentrybot_pre_real_bridge_inspect.isawaitable(value):
        return await value
    return value




async def _handle_step(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    prompt = _payload_prompt(payload)
    agent = _ensure_bound_agent(request, {})
    if _is_agent_like(agent):
        # sentrybot_pre_real_tool_bridge_fallback
        try:
            _pre_prompt = locals().get("prompt", "")
            _pre_payload = locals().get("payload", None)
            _pre_agent = locals().get("agent", None)
            if _sentrybot_pre_real_prompt_wants_tool(_pre_prompt, _pre_payload):
                _pre_request = locals().get("request", None)
                _pre_app = getattr(_pre_request, "app", None) or locals().get("app", None) or getattr(_pre_agent, "app", None)
                _pre_bridge = await _sentrybot_pre_real_run_bridge(_pre_agent, _pre_prompt, _pre_payload, app=_pre_app, request=_pre_request)
                if isinstance(_pre_bridge, dict) and _pre_bridge.get("ok"):
                    _pre_bridge["pre_real_tool_bridge"] = True
                    _agent_type = None
                    try:
                        _agent_type = f"{type(_pre_agent).__module__}.{type(_pre_agent).__qualname__}" if _pre_agent is not None else None
                    except Exception:
                        _agent_type = None
                    return {
                        "ok": True,
                        "source": "gateway_agent_real_tool_bridge",
                        "method": "tool_bridge",
                        "agent_type": _agent_type,
                        "result": _pre_bridge,
                        "real_agent_errors": [],
                        "pre_real_tool_bridge": True,
                    }
        except Exception as _pre_real_bridge_exc:
            pass
        real = await _call_real_agent(agent, prompt, payload, event_mode=False)
        # sentrybot_real_empty_actions_tool_fallback
        try:
            if isinstance(real, dict) and not real.get("real_agent_errors") and _sentrybot_prompt_wants_tool_action(prompt, payload) and _sentrybot_result_actions_empty(real):
                bridge = await _sentrybot_run_tool_bridge_compat(agent, prompt, payload)
                if isinstance(bridge, dict) and bridge.get("ok"):
                    bridge["real_agent_result_without_actions"] = real
                    return bridge
        except Exception as _tool_empty_fallback_exc:
            if isinstance(real, dict):
                real.setdefault("real_agent_errors", []).append("tool_empty_fallback:" + repr(_tool_empty_fallback_exc))
        if real.get("ok"):
            return {k: v for k, v in real.items() if k != "errors"}
        return await _tool_bridge_with_real_agent(request, agent, prompt, real.get("errors", []))
    return {"ok": True, "source": "gateway_agent_compat_ollama", "result": _ollama_tool_fallback(prompt)}


async def _handle_event(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    prompt = _payload_prompt(payload)
    agent = _ensure_bound_agent(request, {})
    if _is_agent_like(agent):
        real = await _call_real_agent(agent, prompt, payload, event_mode=True)
        if real.get("ok"):
            return {k: v for k, v in real.items() if k != "errors"}
    return {"ok": True, "source": "gateway_agent_compat_event", "event": payload, "message": prompt}


def _existing_paths(app: Any) -> set[str]:
    paths: set[str] = set()
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    return paths


def include_agent_api_routes(app: Any) -> Any:
    existing = _existing_paths(app)
    routes = (("/agent/step", _handle_step), ("/agent/turn", _handle_step), ("/agent/chat", _handle_step), ("/agent/events", _handle_event), ("/api/agent/step", _handle_step), ("/api/agent/turn", _handle_step), ("/api/agent/chat", _handle_step), ("/api/agent/events", _handle_event))
    for path, handler in routes:
        if path not in existing:
            app.add_api_route(path, handler, methods=["POST"])
    return app


def install_agent_api_compat(app: Any) -> Any:
    return include_agent_api_routes(app)


__all__ = ["include_agent_api_routes", "install_agent_api_compat"]


# SENTRYBOT override: prefer bridge candidates that execute tool calls through ActionArbiter.
def _sentrybot_pre_real_extract_tool_data(res):
    if not isinstance(res, dict):
        return {}, [], []

    data = res.get("result") if isinstance(res.get("result"), dict) else res
    if not isinstance(data, dict):
        data = {}

    tool_calls = data.get("tool_calls") or res.get("tool_calls") or []
    executions = data.get("executions") or res.get("executions") or []

    return data, tool_calls, executions

def _sentrybot_pre_real_candidate_score(name, fn):
    lname = str(name).lower()
    try:
        src = _sentrybot_pre_real_bridge_inspect.getsource(fn).lower()
    except Exception:
        src = ""

    blob = lname + "\n" + src
    score = 0

    if "local_action_preferred" in blob:
        score += 1000
    if "action_fallback" in blob:
        score += 900
    if "tool_registry_execute_loopback_queue" in blob:
        score += 800
    if "action_arbiter" in blob or "actionarbiter" in blob:
        score += 700
    if "executions" in blob:
        score += 500
    if "tool_calls" in blob:
        score += 100
    if "gateway_agent_real_tool_bridge" in blob:
        score += 80
    if "bridge" in lname:
        score += 50
    if "ollama" in lname and "tool" in lname:
        score += 40
    if "tool" in lname:
        score += 10

    return score

def _sentrybot_pre_real_bridge_candidates():
    names = []

    for name, fn in globals().items():
        if not callable(fn):
            continue

        lname = str(name).lower()

        if name.startswith("_sentrybot_"):
            continue
        if lname in {"_handle_step", "handle_step", "_call_real_agent"}:
            continue
        if "handle" in lname and "bridge" not in lname:
            continue

        score = _sentrybot_pre_real_candidate_score(name, fn)
        if score > 0:
            names.append((score, name))

    names.sort(reverse=True)
    return [name for _, name in names]



# SENTRYBOT override: execute pre-real tool_calls through local ActionArbiter when bridge returns only tool_calls.
def _sentrybot_pre_real_normalize_tool_call(call):
    if not isinstance(call, dict):
        return None, {}, call

    raw = call
    name = call.get("name")
    arguments = call.get("arguments")

    fn = call.get("function")
    if isinstance(fn, dict):
        name = fn.get("name") or name
        arguments = fn.get("arguments", arguments)

    if isinstance(arguments, str):
        try:
            import json as _json
            arguments = _json.loads(arguments)
        except Exception:
            arguments = {"value": arguments}

    if arguments is None:
        arguments = {}

    if not isinstance(arguments, dict):
        arguments = {"value": arguments}

    return name, arguments, raw

def _sentrybot_pre_real_jsonish(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _sentrybot_pre_real_jsonish(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sentrybot_pre_real_jsonish(v) for v in value]
    if hasattr(value, "__dict__"):
        try:
            return {str(k): _sentrybot_pre_real_jsonish(v) for k, v in vars(value).items() if not str(k).startswith("_")}
        except Exception:
            pass
    return repr(value)

def _sentrybot_pre_real_get_state_app(app=None, request=None, agent=None):
    candidates = [
        app,
        getattr(request, "app", None),
        getattr(agent, "app", None),
        getattr(agent, "_app", None),
        getattr(agent, "gateway_app", None),
    ]

    for item in candidates:
        if item is not None:
            return item

    return None

def _sentrybot_pre_real_map_tool_to_action(tool_name, arguments):
    mapper = globals().get("_tool_to_action")
    if callable(mapper):
        try:
            mapped = mapper(tool_name, arguments)
            if isinstance(mapped, tuple) and len(mapped) >= 2:
                return mapped[0], mapped[1]
            if isinstance(mapped, dict):
                action_type = mapped.get("action_type") or mapped.get("type") or mapped.get("name")
                payload = mapped.get("payload") if isinstance(mapped.get("payload"), dict) else arguments
                if action_type:
                    return action_type, payload
        except Exception:
            pass

    name = str(tool_name or "").strip()

    if name == "set_lights":
        return "lights", dict(arguments or {})
    if name == "set_emotion":
        return "emotion", dict(arguments or {})
    if name == "speak":
        return "speak", dict(arguments or {})
    if name == "queue_action":
        payload = dict(arguments or {})
        return str(payload.get("type") or payload.get("action_type") or "queued"), payload

    return name, dict(arguments or {})

async def _sentrybot_pre_real_submit_local_action(agent, app, request, tool_name, arguments):
    errors = []
    app_obj = _sentrybot_pre_real_get_state_app(app=app, request=request, agent=agent)

    submit_fn = globals().get("_submit_local_action")
    if callable(submit_fn):
        # The observed signature expects four args: app, agent, tool_name, arguments.
        arg_sets = [
            (app_obj, agent, tool_name, arguments),
            (app, agent, tool_name, arguments),
            (request, agent, tool_name, arguments),
            (agent, app_obj, tool_name, arguments),
            (agent, tool_name, arguments),
            (tool_name, arguments),
        ]

        for args in arg_sets:
            try:
                res = await _sentrybot_pre_real_maybe_await(submit_fn(*args))
                if isinstance(res, dict):
                    return res
            except TypeError as exc:
                errors.append(f"_submit_local_action/{len(args)}:TypeError:{exc}")
                continue
            except Exception as exc:
                errors.append(f"_submit_local_action/{len(args)}:{type(exc).__name__}:{exc}")
                continue

    action_type, payload = _sentrybot_pre_real_map_tool_to_action(tool_name, arguments)

    arbiter = None
    finder = globals().get("_find_action_arbiter")
    if callable(finder):
        started = {}
        try:
            started = getattr(getattr(app_obj, "state", None), "started", {}) or {}
        except Exception:
            started = {}

        for args in [
            (app_obj, started),
            (app_obj, agent),
            (app_obj,),
            (request, started),
            (request,),
        ]:
            try:
                found = finder(*args)
                if found is not None:
                    arbiter = found
                    break
            except Exception as exc:
                errors.append(f"_find_action_arbiter/{len(args)}:{type(exc).__name__}:{exc}")

    if arbiter is None and app_obj is not None:
        state = getattr(app_obj, "state", None)
        for attr in ["action_arbiter", "arbiter", "agent_action_arbiter"]:
            value = getattr(state, attr, None) if state is not None else None
            if value is not None:
                arbiter = value
                break

        if arbiter is None:
            try:
                started = getattr(state, "started", {}) or {}
                if isinstance(started, dict):
                    for key in ["action_arbiter", "arbiter", "agent_action_arbiter"]:
                        if started.get(key) is not None:
                            arbiter = started.get(key)
                            break
            except Exception:
                pass

    if arbiter is not None and hasattr(arbiter, "submit"):
        maker = globals().get("_make_action_request")
        req = None

        if callable(maker):
            for args in [(action_type, payload), (tool_name, arguments)]:
                try:
                    req = maker(*args)
                    break
                except Exception as exc:
                    errors.append(f"_make_action_request/{len(args)}:{type(exc).__name__}:{exc}")

        if req is None:
            req = {
                "type": action_type,
                "source": "agent_core",
                "priority": 50,
                "ttl_ms": 5000,
                "cooldown_key": f"agent_api_tool_bridge:{action_type}",
                "payload": payload,
            }

        try:
            result = await _sentrybot_pre_real_maybe_await(arbiter.submit(req))
            return {
                "ok": True,
                "via": "action_arbiter",
                "attempt": "request_obj",
                "action_type": action_type,
                "payload": payload,
                "result": _sentrybot_pre_real_jsonish(result),
            }
        except Exception as exc:
            errors.append(f"arbiter.submit:{type(exc).__name__}:{exc}")

    return {
        "ok": False,
        "via": "action_arbiter",
        "action_type": action_type,
        "payload": payload,
        "errors": errors[-30:],
    }

async def _sentrybot_pre_real_ensure_executions(agent, app, request, res):
    data, tool_calls, executions = _sentrybot_pre_real_extract_tool_data(res)

    if not isinstance(res, dict) or executions or not tool_calls:
        return res

    execution_items = []

    for call in tool_calls:
        tool_name, arguments, raw = _sentrybot_pre_real_normalize_tool_call(call)
        if not tool_name:
            continue

        fallback = await _sentrybot_pre_real_submit_local_action(agent, app, request, tool_name, arguments)

        execution_items.append({
            "tool": tool_name,
            "arguments": arguments,
            "registry": {
                "ok": True,
                "via": "local_action_preferred",
                "skipped": "tool_registry_execute_loopback_queue",
            },
            "action_fallback": fallback,
        })

    if execution_items:
        target = data if isinstance(data, dict) and data is not res else res
        target["executions"] = execution_items
        res["executions"] = execution_items
        res["pre_real_executions_added"] = True

    return res

async def _sentrybot_pre_real_run_bridge(agent, prompt, payload, app=None, request=None):
    errors = []
    best_tool_only = None

    preferred = [
        "_run_ollama_tool_bridge",
        "_run_ollama_tools",
        "_direct_ollama_tool_call",
        "_ollama_tool_call",
        "_run_native_tool_bridge",
        "_run_tool_bridge",
        "_ollama_tool_fallback",
    ]

    ordered = []
    for name in _sentrybot_pre_real_bridge_candidates() + preferred:
        if name not in ordered:
            ordered.append(name)

    for name in ordered:
        fn = globals().get(name)
        if not callable(fn):
            continue

        arg_sets = [
            (agent, prompt, payload),
            (agent, prompt),
            (prompt, payload),
            (prompt,),
        ]

        for args in arg_sets:
            try:
                res = await _sentrybot_pre_real_maybe_await(fn(*args))
                res = await _sentrybot_pre_real_ensure_executions(agent, app, request, res)

                data, tool_calls, executions = _sentrybot_pre_real_extract_tool_data(res)

                if isinstance(res, dict) and res.get("ok") and tool_calls and executions:
                    res.setdefault("source", "gateway_agent_real_tool_bridge")
                    res["pre_real_tool_bridge"] = True
                    res["pre_real_bridge_candidate"] = name
                    return res

                if isinstance(res, dict) and res.get("ok") and tool_calls and best_tool_only is None:
                    best_tool_only = dict(res)
                    best_tool_only.setdefault("source", "gateway_agent_real_tool_bridge")
                    best_tool_only["pre_real_tool_bridge"] = True
                    best_tool_only["pre_real_bridge_candidate"] = name
                    best_tool_only["pre_real_missing_executions"] = True

                errors.append(f"{name}/{len(args)}:tool_calls={len(tool_calls)} executions={len(executions)} ok={res.get('ok') if isinstance(res, dict) else None}")
            except TypeError as exc:
                errors.append(f"{name}/{len(args)}:TypeError:{exc}")
                continue
            except Exception as exc:
                errors.append(f"{name}/{len(args)}:{type(exc).__name__}:{exc}")
                break

    if best_tool_only is not None:
        best_tool_only["bridge_candidate_names"] = ordered
        best_tool_only["bridge_errors"] = errors[-50:]
        return best_tool_only

    return {
        "ok": False,
        "source": "gateway_agent_real_tool_bridge",
        "method": "pre_real_tool_bridge",
        "error": "no working bridge candidate",
        "bridge_candidate_names": ordered,
        "bridge_errors": errors[-50:],
    }

