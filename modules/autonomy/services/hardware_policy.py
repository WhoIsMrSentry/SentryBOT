from __future__ import annotations

from typing import Any, Dict, Optional


def apply_runtime_hardware_policy(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bind dry-run / real-hardware flags to the Pi execution profile.

    PC and tests stay dry-run. A detected Raspberry Pi with
    ``config/robot_execution_profiles.json`` may enable real motion.
    Set ``follow_runtime_profile: false`` to keep YAML flags as-is.
    """
    out = dict(cfg or {})
    if not bool(out.get("follow_runtime_profile", True)):
        out.setdefault("runtime_profile_applied", False)
        return out

    from .robot_runtime_profile import status as runtime_status

    st = runtime_status()
    out["runtime_profile_applied"] = True
    out["runtime_reason"] = st.get("reason")
    if st.get("ok"):
        out["allow_real_hardware"] = bool(st.get("allow_real_hardware", True))
        if out["allow_real_hardware"] and out.get("dry_run_on_pi") is not True:
            out["dry_run_default"] = False
        return out

    out["allow_real_hardware"] = False
    out["dry_run_default"] = True
    return out


__all__ = ["apply_runtime_hardware_policy"]
