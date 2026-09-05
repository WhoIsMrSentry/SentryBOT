from __future__ import annotations
import json
from typing import Any, Dict, List, Tuple

def payload_prompt(payload: Dict[str, Any]) -> str:
    """Extract user prompt from generic gateway payload."""
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

def normalize_tool_call(tc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw tool call dictionary into {name, arguments, raw}."""
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

def extract_tool_data(res: Any) -> Tuple[Dict[str, Any], List[Any], List[Any]]:
    """Extract structured data, tool_calls and executions from result."""
    if not isinstance(res, dict):
        return {}, [], []

    data = res.get("result") if isinstance(res.get("result"), dict) else res
    if not isinstance(data, dict):
        data = {}

    tool_calls = data.get("tool_calls") or res.get("tool_calls") or []
    executions = data.get("executions") or res.get("executions") or []
    return data, list(tool_calls), list(executions)
