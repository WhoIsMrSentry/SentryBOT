from __future__ import annotations

# SENTRYBOT: ActionRequest priority must be numeric for ActionArbiter.submit.

import inspect
import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import Request

# Consolidated duplicates (audit FIX-12): both legacy helpers now live in
# modules.common.ollama_url; local names kept as aliases for call sites.
from modules.common.ollama_url import (  # noqa: E402,F401
    ensure_ollama_host_env as _ensure_ollama_host_env,
    ensure_sentrybot_ollama_host_env as _sentrybot_ensure_ollama_host_env,
)

DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_OLLAMA_BASE_URL = "http://whoismrsentry.local:11434"
_AGENT_STATE_NAMES = ("agent_service", "agent", "agent_core", "agent_runtime", "sentrybot_agent")

_TOOL_ACTION_KEYWORDS = (
    "set_lights", "lights", "light", "neopixel", "led", "rgb",
    "emotion", "set_emotion", "speak", "say", "queue_action",
    "tool", "use the", "using the", "execute", "run",
    "red", "green", "blue", "solid", "rainbow", "blink",
)

_REFUSAL_SNIPPETS = (
    "can't actually control",
    "cannot execute external tools",
    "cannot directly control",
    "don't have direct control",
    "i cannot execute",
    "i can't actually",
    "hypothetical",
    "example implementation",
)


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
    return obj is not None and any(
        callable(getattr(obj, name, None))
        for name in ("step", "step_event", "turn", "chat", "run", "handle_event")
    )


def _find_agent_service(request: Request) -> Any:
    for name in _AGENT_STATE_NAMES:
        svc = _state_get(request.app, name)
        if _is_agent_like(svc):
            return svc
    for container_name in ("started", "services"):
        container = _state_get(request.app, container_name)
        if isinstance(container, dict):
            for name in _AGENT_STATE_NAMES:
                svc = container.get(name)
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


async def _call_real_agent(
    agent: Any, prompt: str, payload: Dict[str, Any], event_mode: bool = False
) -> Dict[str, Any]:
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
                    return {
                        "ok": True,
                        "source": "gateway_agent_real",
                        "method": method_name,
                        "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
                        "result": result,
                        "errors": errors,
                    }
                errors.append(f"{method_name}.{label}:inert_result:{result!r}")
            except Exception as exc:
                errors.append(f"{method_name}.{label}:{type(exc).__name__}:{exc}")
    return {
        "ok": False,
        "source": "gateway_agent_real_inert",
        "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
        "errors": errors[-20:],
    }


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
    value = (
        os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
        or os.getenv("SENTRYBOT_REMOTE_OLLAMA_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or DEFAULT_OLLAMA_BASE_URL
    )
    return str(value).rstrip("/")


def _ollama_model() -> str:
    return str(
        os.getenv("SENTRYBOT_OLLAMA_MODEL")
        or os.getenv("SENTRYBOT_MODEL")
        or os.getenv("SENTRYBOT_LLM_MODEL")
        or DEFAULT_MODEL
    )


def _minimal_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "set_lights",
                "description": "Set robot lights safely.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "effect": {
                            "type": "string",
                            "enum": ["solid", "pulse", "off", "SOLID", "PULSE", "OFF"],
                        },
                        "color": {"type": "string"},
                    },
                    "required": ["effect", "color"],
                },
            },
        }
    ]


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
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": "Use the provided tool when appropriate. Return a tool call only when the user asks for robot action.",
            },
            {"role": "user", "content": prompt},
        ],
        "tools": tools or _minimal_tools(),
        "options": {"temperature": 0, "num_predict": 128},
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    message = data.get("message") or {}
    raw_tool_calls = message.get("tool_calls") or []
    return {
        "ok": True,
        "provider": "ollama",
        "model": model,
        "base_url": base_url,
        "tool_calls": [_normalize_tool_call(x) for x in raw_tool_calls if isinstance(x, dict)],
        "content": message.get("content", ""),
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _registry_result_needs_action_fallback(result: Any) -> bool:
    text = repr(result)
    needles = (
        "Queue action failed",
        "HTTPConnectionPool",
        "ConnectTimeoutError",
        "127.0.0.1",
        "/agent/actions/queue",
        "connection timed out",
        "Max retries exceeded",
    )
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
    attempts = (
        ("name_args", (tool_name, arguments), {}),
        ("name_kwargs", (tool_name,), dict(arguments)),
        ("keyword", (), {"name": tool_name, "arguments": arguments}),
        ("tool_keyword", (), {"tool_name": tool_name, "args": arguments}),
    )
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
            if (
                obj is not None
                and callable(getattr(obj, "submit", None))
                and obj.__class__.__name__.lower().endswith("arbiter")
            ):
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

        return ActionRequest(
            type=action_type,
            source=source_value,
            priority=priority_value,
            ttl_ms=5000,
            cooldown_key=cooldown_key,
            payload=payload,
        )
    except Exception:
        return fallback


def _submit_local_action(
    request: Request, agent: Any, tool_name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    arbiter = _find_action_arbiter(request, agent)
    if arbiter is None:
        return {"ok": False, "via": "action_arbiter", "error": "action_arbiter_not_found"}
    submit = getattr(arbiter, "submit", None)
    if not callable(submit):
        return {"ok": False, "via": "action_arbiter", "error": "submit_not_callable"}
    action_type, payload = _tool_to_action(tool_name, arguments)
    request_obj = _make_action_request(action_type, payload)
    errors: List[str] = []
    attempts = (
        ("request_obj", (request_obj,), {}),
        (
            "dict",
            (
                {
                    "type": action_type,
                    "action_type": action_type,
                    "payload": payload,
                    "source": "agent_api_tool_bridge",
                },
            ),
            {},
        ),
        ("type_payload", (action_type, payload), {}),
        ("keywords", (), {"action_type": action_type, "payload": payload, "source": "agent_api_tool_bridge"}),
        ("type_keyword", (), {"type": action_type, "payload": payload, "source": "agent_api_tool_bridge"}),
    )
    for label, args, kwargs in attempts:
        try:
            result = submit(*args, **kwargs)
            return {
                "ok": True,
                "via": "action_arbiter",
                "attempt": label,
                "action_type": action_type,
                "payload": payload,
                "result": result,
            }
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{exc}")
    return {
        "ok": False,
        "via": "action_arbiter",
        "action_type": action_type,
        "payload": payload,
        "errors": errors[-10:],
    }


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


async def _tool_bridge_with_real_agent(
    request: Request,
    agent: Any,
    prompt: str,
    real_errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
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

        if action_result is None and (
            (not registry_result.get("ok"))
            or _registry_result_needs_action_fallback(registry_result.get("result"))
        ):
            action_result = _submit_local_action(request, agent, tool_name, arguments)

        executions.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "registry": registry_result,
                "action_fallback": action_result,
            }
        )

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


def _prompt_wants_tool_action(prompt: str, payload: object = None) -> bool:
    hay = (str(prompt or "") + " " + str(payload or "")).lower()
    return any(k in hay for k in _TOOL_ACTION_KEYWORDS)


def _result_actions_empty(result: object) -> bool:
    if result is None:
        return True
    data = result.get("result") if isinstance(result, dict) and isinstance(result.get("result"), dict) else result
    if not isinstance(data, dict):
        return False
    actions = data.get("actions")
    if isinstance(actions, list) and len(actions) > 0:
        return False
    text = str(data.get("text") or data.get("content") or "").lower()
    if isinstance(actions, list) and len(actions) == 0:
        return True
    return any(bit in text for bit in _REFUSAL_SNIPPETS)


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
        if _prompt_wants_tool_action(prompt, payload):
            try:
                bridge = await _tool_bridge_with_real_agent(request, agent, prompt)
                bridge_res = bridge.get("result", {}) if isinstance(bridge, dict) else {}
                if (
                    isinstance(bridge, dict)
                    and bridge.get("ok")
                    and bridge_res.get("tool_calls")
                    and bridge_res.get("executions")
                ):
                    bridge["pre_real_tool_bridge"] = True
                    return bridge
            except Exception:
                pass

        real = await _call_real_agent(agent, prompt, payload, event_mode=False)
        if (
            isinstance(real, dict)
            and not real.get("real_agent_errors")
            and _prompt_wants_tool_action(prompt, payload)
            and _result_actions_empty(real)
        ):
            try:
                bridge = await _tool_bridge_with_real_agent(request, agent, prompt)
                if isinstance(bridge, dict) and bridge.get("ok"):
                    bridge["real_agent_result_without_actions"] = real
                    return bridge
            except Exception as exc:
                real.setdefault("real_agent_errors", []).append(f"tool_empty_fallback:{exc!r}")

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
    routes = (
        ("/agent/step", _handle_step),
        ("/agent/turn", _handle_step),
        ("/agent/chat", _handle_step),
        ("/agent/events", _handle_event),
        ("/api/agent/step", _handle_step),
        ("/api/agent/turn", _handle_step),
        ("/api/agent/chat", _handle_step),
        ("/api/agent/events", _handle_event),
    )
    for path, handler in routes:
        if path not in existing:
            app.add_api_route(path, handler, methods=["POST"])
    return app


def install_agent_api_compat(app: Any) -> Any:
    return include_agent_api_routes(app)


__all__ = ["include_agent_api_routes", "install_agent_api_compat"]
