from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def strip_code_fence(content: str) -> str:
    text = str(content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def loads_first_json_object(text: str) -> Optional[Any]:
    """Parse text as JSON; if that fails, extract the first balanced {...} block."""
    candidate = str(text or "").strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Extract first outer {...}
    start = candidate.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(candidate)):
        ch = candidate[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start : i + 1])
                    except Exception:
                        return None
    return None


def build_provider_tool_instruction(tools: List[Dict[str, Any]]) -> str:
    names = [str(t.get("function", {}).get("name", "")).strip() for t in tools]
    names = [n for n in names if n]
    if not names:
        return ""
    joined = ", ".join(names)
    return (
        "You may choose at most one tool from this list: "
        f"{joined}. "
        "If a tool is required, reply with ONLY strict JSON: "
        '{"tool":"tool_name","arguments":{...}}. '
        "If no tool is needed, reply with plain text only."
    )


def parse_provider_tool_call(
    content: str, tools: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not content or not tools:
        return None

    allowed = {
        str(t.get("function", {}).get("name", "")).strip()
        for t in tools
        if str(t.get("function", {}).get("name", "")).strip()
    }
    cleaned = strip_code_fence(content)
    data = loads_first_json_object(cleaned)
    if not isinstance(data, dict):
        return None

    tool_name = str(
        data.get("tool") or data.get("tool_name") or data.get("name") or ""
    ).strip()
    if tool_name not in allowed:
        return None

    arguments = data.get("arguments", data.get("args", data.get("parameters", {})))
    if not isinstance(arguments, dict):
        arguments = {}

    return {
        "function": {
            "name": tool_name,
            "arguments": arguments,
        }
    }
