"""Apply ``runtime_profile`` from agent.yaml to top-level module sections.

Switch backends by editing only::

    runtime_profile:
      active: google_ai_studio   # or remote_ollama
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from modules.config_center.agent_yaml_loader import deep_merge


def _deep_merge_profile(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge profile patch; do not overwrite with empty strings/null."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_profile(dict(out[key]), value)
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


_PROFILE_SECTION_KEYS: tuple[str, ...] = (
    "agent",
    "llm",
    "ollama",
    "google_ai_studio",
    "ollama_service",
    "vlm_bridge",
    "arduino_serial",
    "esp_link",
    "speak",
    "speech",
    "tri_layer",
    "realtime_profile",
    "safety",
)


def apply_runtime_profile(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the active runtime profile into *cfg* (in place) and return it."""
    profile_root = cfg.get("runtime_profile")
    if not isinstance(profile_root, dict):
        return cfg

    active = str(profile_root.get("active", "")).strip()
    profiles = profile_root.get("profiles")
    if not active or not isinstance(profiles, dict):
        return cfg

    patch = profiles.get(active)
    if not isinstance(patch, dict):
        return cfg

    for key in _PROFILE_SECTION_KEYS:
        section_patch = patch.get(key)
        if not isinstance(section_patch, dict):
            continue
        existing = cfg.get(key)
        if isinstance(existing, dict):
            cfg[key] = _deep_merge_profile(dict(existing), section_patch)
        else:
            cfg[key] = dict(section_patch)

    cfg["_runtime_profile_active"] = active
    return cfg


def list_runtime_profiles(cfg: Dict[str, Any]) -> List[str]:
    profile_root = cfg.get("runtime_profile")
    if not isinstance(profile_root, dict):
        return []
    profiles = profile_root.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return sorted(str(name) for name in profiles.keys())


def active_runtime_profile(cfg: Dict[str, Any]) -> str:
    explicit = str(cfg.get("_runtime_profile_active", "")).strip()
    if explicit:
        return explicit
    profile_root = cfg.get("runtime_profile")
    if isinstance(profile_root, dict):
        return str(profile_root.get("active", "")).strip()
    return ""
