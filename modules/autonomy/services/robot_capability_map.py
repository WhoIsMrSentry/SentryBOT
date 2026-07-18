# Read-only robot capability source-of-truth adapter.
#
# This module intentionally does not enable hardware and does not execute actions.
# It exposes the configured capability registry to runtime/autonomy code so tools
# and runtime can share one canonical capability source.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


ROBOT_CAPABILITY_SOURCE_OF_TRUTH = True
ROBOT_CAPABILITY_BOUNDARY_ROLE = "autonomy_read_only_capability_registry_adapter"
ROBOT_CAPABILITY_CONFIG_PATH = "config/robot_capability_registry.json"
ROBOT_CAPABILITY_RUNTIME_OWNER = "modules.autonomy reads capability registry; hard safety/arm gates remain in tools/ci and execution gates"
ROBOT_CAPABILITY_BOUNDARY_REASON = (
    "Capability registry lives in config/robot_capability_registry.json. "
    "This adapter makes that registry available to autonomy without enabling real hardware."
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def registry_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else _project_root()
    return base / ROBOT_CAPABILITY_CONFIG_PATH


def load_registry(root: Optional[Path] = None) -> Dict[str, Any]:
    path = registry_path(root)
    if not path.exists():
        return {
            "ok": False,
            "available": False,
            "reason": "robot_capability_registry_missing",
            "path": str(path),
            "capabilities": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "reason": "robot_capability_registry_invalid_json",
            "path": str(path),
            "error": str(exc),
            "capabilities": {},
        }

    if not isinstance(data, dict):
        return {
            "ok": False,
            "available": False,
            "reason": "robot_capability_registry_not_object",
            "path": str(path),
            "capabilities": {},
        }

    data = dict(data)
    data.setdefault("ok", True)
    data.setdefault("available", True)
    data.setdefault("path", str(path))
    data.setdefault("source", ROBOT_CAPABILITY_CONFIG_PATH)
    return data


def _capability_items(registry: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("capabilities", "registry", "items", "actions"):
        value = registry.get(key)
        if isinstance(value, dict):
            return value
    metadata = {
        "ok", "available", "path", "source", "version", "updated_at",
        "profiles", "defaults", "metadata", "schema", "reason", "error",
    }
    candidates = {k: v for k, v in registry.items() if k not in metadata}
    return candidates if candidates else {}


def list_capabilities(root: Optional[Path] = None) -> List[str]:
    registry = load_registry(root)
    return sorted(str(k) for k in _capability_items(registry).keys())


def get_capability(name: str, root: Optional[Path] = None) -> Dict[str, Any]:
    key = str(name or "").strip()
    registry = load_registry(root)
    items = _capability_items(registry)
    value = items.get(key)
    if isinstance(value, dict):
        out = dict(value)
        out.setdefault("name", key)
        out.setdefault("available", True)
        return out
    if value is not None:
        return {"name": key, "available": True, "value": value}
    return {"name": key, "available": False, "reason": "capability_not_found"}


def status(root: Optional[Path] = None) -> Dict[str, Any]:
    registry = load_registry(root)
    names = list_capabilities(root)
    return {
        "ok": bool(registry.get("ok", False)),
        "available": bool(registry.get("available", False)),
        "source": registry.get("source", ROBOT_CAPABILITY_CONFIG_PATH),
        "path": registry.get("path"),
        "capability_count": len(names),
        "capabilities": names,
        "read_only": True,
        "hardware_enabled": False,
        "armed": False,
    }


__all__ = [
    "ROBOT_CAPABILITY_SOURCE_OF_TRUTH",
    "ROBOT_CAPABILITY_BOUNDARY_ROLE",
    "ROBOT_CAPABILITY_CONFIG_PATH",
    "ROBOT_CAPABILITY_RUNTIME_OWNER",
    "ROBOT_CAPABILITY_BOUNDARY_REASON",
    "registry_path",
    "load_registry",
    "list_capabilities",
    "get_capability",
    "status",
]
