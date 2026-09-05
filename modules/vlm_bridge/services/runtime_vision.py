from __future__ import annotations

from typing import Any, Dict, Optional


def apply_runtime_vision_profile(vision_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """On Raspberry Pi, overlay production vision flags from robot_execution_profiles.json.

    Field default is local tracking with hybrid capture. PC keeps YAML as-is.
    """
    out = dict(vision_cfg or {})
    if not bool(out.get("follow_runtime_profile", True)):
        return out
    try:
        from modules.autonomy.services.robot_runtime_profile import resolve_runtime_profile

        resolved = resolve_runtime_profile()
    except Exception:
        return out
    if not resolved.get("ok"):
        return out
    profile = resolved.get("profile") if isinstance(resolved.get("profile"), dict) else {}
    vis = profile.get("vision") if isinstance(profile.get("vision"), dict) else {}
    if vis:
        out.update(vis)
    return out


__all__ = ["apply_runtime_vision_profile"]
