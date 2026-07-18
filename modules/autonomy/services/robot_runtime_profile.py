from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from modules.common.runtime_target import detect_runtime_target


PROFILE_PATH = "config/robot_execution_profiles.json"
PROFILE_NAME = "raspberry_pi"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def profile_config_path(root: Optional[Path] = None) -> Path:
    return (Path(root) if root is not None else _project_root()) / PROFILE_PATH


def load_profile_config(root: Optional[Path] = None) -> Dict[str, Any]:
    path = profile_config_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ok": False, "reason": "profile_missing", "path": str(path), "profiles": {}}
    except Exception as exc:
        return {"ok": False, "reason": "profile_invalid", "path": str(path), "error": str(exc), "profiles": {}}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "profile_not_object", "path": str(path), "profiles": {}}
    data = dict(data)
    data["ok"] = True
    data["path"] = str(path)
    return data


def resolve_runtime_profile(root: Optional[Path] = None) -> Dict[str, Any]:
    target = detect_runtime_target()
    cfg = load_profile_config(root)
    profiles = cfg.get("profiles") if isinstance(cfg.get("profiles"), dict) else {}
    profile = profiles.get(PROFILE_NAME) if isinstance(profiles.get(PROFILE_NAME), dict) else {}
    return {
        "ok": bool(target.is_raspberry_pi and cfg.get("ok") and profile),
        "target": target.to_dict(),
        "profile_name": PROFILE_NAME,
        "profile": dict(profile),
        "config_path": cfg.get("path"),
        "reason": "ready" if target.is_raspberry_pi else target.reason,
    }


def status(root: Optional[Path] = None) -> Dict[str, Any]:
    resolved = resolve_runtime_profile(root)
    profile = resolved.get("profile") if isinstance(resolved.get("profile"), dict) else {}
    return {
        "ok": bool(resolved.get("ok")),
        "target": resolved.get("target", {}),
        "profile_name": PROFILE_NAME,
        "allow_real_hardware": bool(profile.get("allow_real_hardware", True)),
        "allowed_risks": list(profile.get("allowed_risks") or ["none", "low", "medium"]),
        "reason": resolved.get("reason"),
    }


__all__ = ["PROFILE_PATH", "PROFILE_NAME", "profile_config_path", "load_profile_config", "resolve_runtime_profile", "status"]
