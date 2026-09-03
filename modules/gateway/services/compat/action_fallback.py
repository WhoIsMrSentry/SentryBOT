from __future__ import annotations
import inspect
from typing import Any, Dict, Optional, Tuple

async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value

def map_tool_to_action(tool_name: str, arguments: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    name = str(tool_name or "").strip()
    args = dict(arguments or {})
    if name == "set_lights":
        return "lights", args
    if name == "set_emotion":
        return "emotion", args
    if name == "speak":
        return "speak", args
    if name == "queue_action":
        return str(args.get("type") or args.get("action_type") or "queued"), args
    return name, args

def find_action_arbiter(app: Any = None, agent: Any = None) -> Optional[Any]:
    """Resolve the active ActionArbiter instance cleanly without reflection guessing."""
    # Check app state
    if app is not None:
        state = getattr(app, "state", None)
        if state is not None:
            for attr in ("action_arbiter", "arbiter", "agent_action_arbiter"):
                val = getattr(state, attr, None)
                if val is not None:
                    return val
            started = getattr(state, "started", None)
            if isinstance(started, dict):
                for key in ("action_arbiter", "arbiter", "agent_action_arbiter"):
                    if started.get(key) is not None:
                        return started[key]

    # Check agent attributes
    if agent is not None:
        for attr in ("action_arbiter", "arbiter", "_arbiter"):
            val = getattr(agent, attr, None)
            if val is not None:
                return val
    return None

async def submit_action(
    tool_name: str,
    arguments: Dict[str, Any],
    app: Any = None,
    agent: Any = None,
) -> Dict[str, Any]:
    """Submit a tool call action to the ActionArbiter cleanly."""
    action_type, payload = map_tool_to_action(tool_name, arguments)
    arbiter = find_action_arbiter(app, agent)
    if arbiter is not None and hasattr(arbiter, "submit"):
        req = {
            "type": action_type,
            "source": "agent_core",
            "priority": 50,
            "ttl_ms": 5000,
            "cooldown_key": f"agent_api_tool_bridge:{action_type}",
            "payload": payload,
        }
        try:
            res = await _maybe_await(arbiter.submit(req))
            return {
                "ok": True,
                "via": "action_arbiter",
                "action_type": action_type,
                "payload": payload,
                "result": res if isinstance(res, (dict, list, str, int, float, bool)) else repr(res),
            }
        except Exception as exc:
            return {
                "ok": False,
                "via": "action_arbiter",
                "error": str(exc),
                "action_type": action_type,
            }
    return {
        "ok": False,
        "via": "action_arbiter_missing",
        "action_type": action_type,
        "payload": payload,
    }
