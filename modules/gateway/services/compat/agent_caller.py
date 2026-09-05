from __future__ import annotations
import inspect
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gateway.agent_caller")

async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value

class AgentCaller:
    """Invokes agent turns using standardized, typed calls rather than trial-and-error reflection."""

    @staticmethod
    async def call_agent(
        agent: Any,
        prompt: str,
        payload: Dict[str, Any],
        *,
        event_mode: bool = False,
    ) -> Dict[str, Any]:
        if agent is None:
            return {"ok": False, "error": "agent_not_bound"}

        errors: List[str] = []

        # 1. Event mode preference
        if event_mode:
            for method_name in ("step_event", "handle_event"):
                method = getattr(agent, method_name, None)
                if callable(method):
                    try:
                        res = await _maybe_await(method(payload))
                        return {
                            "ok": True,
                            "source": "gateway_agent_real",
                            "method": method_name,
                            "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
                            "result": res,
                        }
                    except Exception as exc:
                        errors.append(f"{method_name}:{exc}")

        # 2. Standard turn/step preference
        for method_name in ("turn", "step", "chat", "run"):
            method = getattr(agent, method_name, None)
            if callable(method):
                try:
                    # Preferred: turn(prompt) or step(prompt)
                    res = await _maybe_await(method(prompt))
                    return {
                        "ok": True,
                        "source": "gateway_agent_real",
                        "method": method_name,
                        "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
                        "result": res,
                    }
                except TypeError:
                    # Alternative: pass payload or keyword
                    try:
                        res = await _maybe_await(method(prompt=prompt))
                        return {
                            "ok": True,
                            "source": "gateway_agent_real",
                            "method": method_name,
                            "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
                            "result": res,
                        }
                    except Exception as exc2:
                        errors.append(f"{method_name}:{exc2}")
                except Exception as exc:
                    errors.append(f"{method_name}:{exc}")

        return {
            "ok": False,
            "source": "gateway_agent_call_failed",
            "agent_type": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
            "errors": errors,
        }
