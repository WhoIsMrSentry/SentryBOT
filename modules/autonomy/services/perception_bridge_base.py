"""Shared conversion helpers for autonomy perception bridges."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {
        "1", "true", "yes", "on", "enabled", "detected", "present", "active", "seen", "ready", "ok"
    }


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, (dict, Mapping)) else {}


def as_list(value: Any, limit: int = 20) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return list(value[:limit])
    return [value]


def compact_text(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


__all__ = ["as_bool", "as_float", "as_dict", "as_list", "compact_text"]

