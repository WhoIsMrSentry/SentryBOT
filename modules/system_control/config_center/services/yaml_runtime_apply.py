"""Map saved module YAML onto :class:`RuntimeConfigRegistry` keys."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.common.config_loader import clear_agent_config_cache

try:
    from .runtime_registry import RuntimeConfigRegistry
except Exception:  # pragma: no cover - degrade import sandbox
    RuntimeConfigRegistry = None  # type: ignore

# Static table mapping (module) -> tuple of (yaml_flat_key, runtime_key_name)
_MODULE_KEY_MAPS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "camera": (
        ("imx500.enabled", "imx500.enabled"),
        ("imx500.confidence", "imx500.confidence"),
    ),
    "neopixel": (
        ("brightness", "brightness"),
        ("fps", "fps"),
        ("default_effect", "default_effect"),
    ),
    "speak": (
        ("tts.rate", "tts.rate"),
        ("tts.volume", "tts.volume"),
        ("tts.engine", "tts.engine"),
    ),
    "autonomy": (
        ("enabled", "enabled"),
        ("tick_interval_s", "tick_interval_s"),
    ),
    "state_manager": (
        ("defaults.operational", "operational"),
    ),
}


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


def _apply_key_pairs(
    registry: "RuntimeConfigRegistry",
    module: str,
    pairs: List[Tuple[str, Any]],
    applied: List[str],
    failed: List[str],
) -> None:
    for key_name, val in pairs:
        ok, msg = _try_set(registry, module, key_name, val)
        (applied if ok else failed).append(msg)


def apply_module_yaml(registry: Optional["RuntimeConfigRegistry"], module: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh config cache and hot-apply mapped runtime knobs after YAML is written."""
    clear_agent_config_cache()
    applied: List[str] = []
    failed: List[str] = []
    if registry is None or RuntimeConfigRegistry is None:
        return {"ok": True, "applied": [], "failed": [], "cache_cleared": True, "requires_runtime_registry": True}

    doc_dict = doc if isinstance(doc, dict) else {}
    flat = _flatten_dict(doc_dict)

    if module == "vlm_bridge":
        pairs: List[Tuple[str, Any]] = []
        for fk, fv in flat.items():
            if fk == "vision.processing_mode":
                pairs.append(("vision.processing_mode", fv))
            elif fk.startswith("vision.mode_categories."):
                suffix = fk[len("vision.mode_categories.") :]
                pairs.append((f"mode_categories.{suffix}", fv))
        vision_block = doc_dict.get("vision", {})
        modes_block = vision_block.get("modes", {}) if isinstance(vision_block, dict) else {}
        if isinstance(modes_block, dict):
            for k, v in modes_block.items():
                pairs.append((f"modes.{k}", v))
        _apply_key_pairs(registry, "vlm_bridge", pairs, applied, failed)
        return {
            "ok": len(failed) == 0,
            "applied": applied,
            "failed": failed,
            "cache_cleared": True,
            "requires_runtime_registry": False,
        }

    key_map = _MODULE_KEY_MAPS.get(module, ())
    pairs = [(runtime_name, flat[yaml_key]) for yaml_key, runtime_name in key_map if yaml_key in flat]
    _apply_key_pairs(registry, module, pairs, applied, failed)

    return {
        "ok": len(failed) == 0,
        "applied": applied,
        "failed": failed,
        "cache_cleared": True,
        "requires_runtime_registry": len(applied) == 0,
    }
