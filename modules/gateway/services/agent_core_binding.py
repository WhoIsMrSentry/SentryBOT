from __future__ import annotations

import os

import importlib
import inspect
import logging
from typing import Any, Dict, Optional, Tuple

# Consolidated duplicate (audit FIX-12): canonical implementation in
# modules.common.ollama_url; legacy local name kept as an alias.
from modules.common.ollama_url import (  # noqa: E402,F401
    ensure_sentrybot_ollama_host_env as _sentrybot_ensure_ollama_host_env,
)


logger = logging.getLogger("gateway.agent_core_binding")

_AGENT_STATE_NAMES = (
    "agent_service",
    "agent",
    "agent_core",
    "agent_runtime",
    "sentrybot_agent",
)

_AGENT_METHODS = (
    "step",
    "step_event",
    "turn",
    "chat",
    "run",
    "handle_event",
)

_AGENT_CANDIDATES = (
    ("modules.agent_core.xAgentCoreService", ("AgentCoreService", "AgentService", "AgentCore")),
    ("modules.agent_core.services.agent", ("AgentOrchestrator", "Agent", "AgentService", "AgentCoreService")),
    ("modules.agent_core.services", ("AgentOrchestrator", "Agent", "AgentService", "AgentCoreService")),
    ("modules.agent_core", ("AgentOrchestrator", "Agent", "AgentCoreService", "AgentService")),
)


def _is_agent_like(obj: Any) -> bool:
    if obj is None:
        return False
    return any(callable(getattr(obj, name, None)) for name in _AGENT_METHODS)


def _bind(app: Any, started: Dict[str, Any], agent: Any, source: str) -> Dict[str, Any]:
    try:
        app.state.agent_service = agent
        app.state.agent = agent
        app.state.agent_core = agent
    except Exception:
        pass

    if isinstance(started, dict):
        started["agent_service"] = agent
        started["agent"] = agent
        started["agent_core"] = agent
        started["_agent_core_binding"] = {
            "ok": True,
            "source": source,
            "type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
        }

    return {
        "ok": True,
        "source": source,
        "type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
        "methods": [name for name in _AGENT_METHODS if callable(getattr(agent, name, None))],
    }


def _state_get(app: Any, name: str) -> Any:
    try:
        return getattr(app.state, name)
    except Exception:
        return None


def _find_existing(app: Any, started: Dict[str, Any]) -> Optional[Tuple[Any, str]]:
    for name in _AGENT_STATE_NAMES:
        obj = _state_get(app, name)
        if _is_agent_like(obj):
            return obj, f"app.state.{name}"

    if isinstance(started, dict):
        for name in _AGENT_STATE_NAMES:
            obj = started.get(name)
            if _is_agent_like(obj):
                return obj, f"started.{name}"

    services = _state_get(app, "services")
    if isinstance(services, dict):
        for name in _AGENT_STATE_NAMES:
            obj = services.get(name)
            if _is_agent_like(obj):
                return obj, f"app.state.services.{name}"

    return None


def _call_attempts(target: Any, app: Any, cfg: Dict[str, Any], started: Dict[str, Any]):
    return (
        ((), {}),
        ((cfg,), {}),
        ((cfg, started), {}),
        ((), {"config": cfg}),
        ((), {"cfg": cfg}),
        ((), {"settings": cfg}),
        ((), {"started": started}),
        ((), {"services": started}),
        ((), {"app": app}),
        ((), {"config": cfg, "started": started}),
        ((), {"cfg": cfg, "started": started}),
        ((), {"config": cfg, "services": started}),
        ((), {"app": app, "config": cfg, "started": started}),
    )


def _construct(target: Any, app: Any, cfg: Dict[str, Any], started: Dict[str, Any]) -> Tuple[Optional[Any], list[str]]:
    errors: list[str] = []

    if _is_agent_like(target) and not inspect.isclass(target):
        return target, errors

    if not callable(target):
        return None, [f"not_callable:{target!r}"]

    for args, kwargs in _call_attempts(target, app, cfg, started):
        try:
            obj = target(*args, **kwargs)
            if _is_agent_like(obj):
                return obj, errors
            errors.append(f"{target}:constructed_not_agent_like:{type(obj).__name__}")
        except TypeError as exc:
            errors.append(f"{target}:type:{exc}")
        except Exception as exc:
            errors.append(f"{target}:error:{type(exc).__name__}:{exc}")

    return None, errors


def _discover_agent(app: Any, cfg: Dict[str, Any], started: Dict[str, Any]) -> Tuple[Optional[Any], str, list[str]]:
    errors: list[str] = []

    for module_name, attr_names in _AGENT_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"{module_name}:import:{type(exc).__name__}:{exc}")
            continue

        for attr_name in attr_names:
            target = getattr(module, attr_name, None)
            if target is None:
                errors.append(f"{module_name}.{attr_name}:missing")
                continue

            obj, obj_errors = _construct(target, app, cfg, started)
            errors.extend(f"{module_name}.{attr_name}:{err}" for err in obj_errors)

            if _is_agent_like(obj):
                return obj, f"{module_name}.{attr_name}", errors

    # Last resort: scan imported candidate modules for any class/object exposing step/step_event.
    for module_name, _ in _AGENT_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue

            target = getattr(module, attr_name, None)
            if not callable(target):
                continue

            if attr_name.lower() not in {"agent", "agentorchestrator", "agentcoreservice", "agentservice", "agentcore"}:
                if "agent" not in attr_name.lower():
                    continue

            obj, obj_errors = _construct(target, app, cfg, started)
            errors.extend(f"{module_name}.{attr_name}:{err}" for err in obj_errors)

            if _is_agent_like(obj):
                return obj, f"{module_name}.{attr_name}", errors

    return None, "not_found", errors


def ensure_agent_core_bound(app: Any, cfg: Optional[Dict[str, Any]] = None, started: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg if isinstance(cfg, dict) else {}

    if started is None or not isinstance(started, dict):
        started = _state_get(app, "started")
        if not isinstance(started, dict):
            started = {}
            try:
                app.state.started = started
            except Exception:
                pass

    existing = _find_existing(app, started)
    if existing is not None:
        agent, source = existing
        return _bind(app, started, agent, source)

    agent, source, errors = _discover_agent(app, cfg, started)
    if _is_agent_like(agent):
        return _bind(app, started, agent, source)

    status = {
        "ok": False,
        "source": source,
        "errors": errors[-80:],
    }

    if isinstance(started, dict):
        started["_agent_core_binding"] = status

    return status


__all__ = ["ensure_agent_core_bound"]
