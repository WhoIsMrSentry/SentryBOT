"""Map saved module YAML onto :class:`RuntimeConfigRegistry` keys (subset)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from .runtime_registry import RuntimeConfigRegistry
except Exception:  # pragma: no cover - degrade import sandbox
    RuntimeConfigRegistry = None  # type: ignore


def _flatten_dict(obj: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (obj or {}).items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten_dict(value, path))
        elif isinstance(value, list):
            continue
        else:
            out[path] = value
    return out


def _try_set(registry: "RuntimeConfigRegistry", module: str, name: str, value: Any) -> Tuple[bool, str]:
    outcome = registry.set(module, name, value, actor="config_set", source="yaml_put")
    if outcome.get("ok"):
        return True, f"{module}.{name}"
    return False, f"{module}.{name} ({outcome.get('error')})"


def apply_module_yaml(registry: Optional["RuntimeConfigRegistry"], module: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Hot-apply a narrow slice of knobs after YAML is written."""
    applied: List[str] = []
    failed: List[str] = []
    if registry is None or RuntimeConfigRegistry is None:
        return {"ok": True, "applied": [], "failed": [], "requires_runtime_registry": True}

    if module == "vlm_bridge":
        flat = _flatten_dict(doc if isinstance(doc, dict) else {})
        for fk, fv in flat.items():
            if fk == "vision.processing_mode":
                ok, msg = _try_set(registry, "vlm_bridge", "vision.processing_mode", fv)
                (applied if ok else failed).append(msg)
            elif fk.startswith("vision.mode_categories."):
                suffix = fk[len("vision.mode_categories.") :]
                ok, msg = _try_set(registry, "vlm_bridge", f"mode_categories.{suffix}", fv)
                (applied if ok else failed).append(msg)
        modes_block = doc.get("vision", {}).get("modes", {}) if isinstance(doc.get("vision", {}), dict) else {}
        if isinstance(modes_block, dict):
            for k, v in modes_block.items():
                ok, msg = _try_set(registry, "vlm_bridge", f"modes.{k}", v)
                (applied if ok else failed).append(msg)
        return {"ok": len(failed) == 0, "applied": applied, "failed": failed, "requires_runtime_registry": False}

    flat = _flatten_dict(doc if isinstance(doc, dict) else {})
    if module == "camera":
        enabled = flat.get("imx500.enabled")
        confidence = flat.get("imx500.confidence")
        if enabled is not None:
            ok, msg = _try_set(registry, "camera", "imx500.enabled", enabled)
            (applied if ok else failed).append(msg)
        if confidence is not None:
            ok, msg = _try_set(registry, "camera", "imx500.confidence", confidence)
            (applied if ok else failed).append(msg)

    return {
        "ok": len(failed) == 0,
        "applied": applied,
        "failed": failed,
        "requires_runtime_registry": len(applied) == 0,
    }
