#!/usr/bin/env python3
"""Safe robot hardware arm-state controller.

This tool is deliberately conservative. In the current PC/refactor profile it
can report status and disarm, but it must refuse real arming while policy keeps
allow_real_hardware=false and allow_pc_arm=false.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "robot_arm_policy.json"
STATE_PATH = ROOT / ".sentrybot_state" / "robot_arm_state.json"

CONFIRM_TEXT = "ARM_SENTRYBOT_HARDWARE"


def _read_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default or {})
    except Exception as exc:
        return {"_error": str(exc), **dict(default or {})}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_policy() -> Dict[str, Any]:
    return _read_json(POLICY_PATH, {
        "enabled": True,
        "default_armed": False,
        "allow_pc_arm": False,
        "allow_real_hardware": False,
        "require_manual_arm": True,
        "max_arm_ttl_s": 300,
    })


def default_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "armed": False,
        "profile": "pc_dry_run",
        "reason": "implicit_default_disarmed",
        "armed_until_ts": 0.0,
    }


def load_state() -> Dict[str, Any]:
    state = _read_json(STATE_PATH, default_state())
    if not isinstance(state.get("armed"), bool):
        state["armed"] = False
    if not state.get("profile"):
        state["profile"] = "pc_dry_run"
    if not isinstance(state.get("armed_until_ts"), (int, float)):
        state["armed_until_ts"] = 0.0
    return state


def save_state(state: Dict[str, Any]) -> None:
    state["updated_ts"] = time.time()
    _write_json(STATE_PATH, state)


def is_expired(state: Dict[str, Any], now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return bool(state.get("armed")) and float(state.get("armed_until_ts") or 0.0) > 0 and now >= float(state.get("armed_until_ts") or 0.0)


def normalized_status() -> Dict[str, Any]:
    policy = load_policy()
    state = load_state()
    expired = is_expired(state)
    if expired:
        state["armed"] = False
        state["reason"] = "arm_ttl_expired"
        state["profile"] = "pc_dry_run"
        state["armed_until_ts"] = 0.0
        save_state(state)
    return {
        "ok": True,
        "armed": bool(state.get("armed")),
        "profile": state.get("profile", "pc_dry_run"),
        "reason": state.get("reason", ""),
        "armed_until_ts": float(state.get("armed_until_ts") or 0.0),
        "expired": expired,
        "policy": {
            "enabled": bool(policy.get("enabled", False)),
            "allow_pc_arm": bool(policy.get("allow_pc_arm", False)),
            "allow_real_hardware": bool(policy.get("allow_real_hardware", False)),
            "require_manual_arm": bool(policy.get("require_manual_arm", True)),
            "max_arm_ttl_s": float(policy.get("max_arm_ttl_s", 300) or 300),
            "allowed_profiles_when_armed": policy.get("allowed_profiles_when_armed") or [],
        },
        "hardware_enabled": bool(policy.get("allow_real_hardware", False)) and bool(state.get("armed")),
    }


def evaluate_arm_request(profile: str, confirm: str, ttl_s: float | None, dry_run: bool) -> Tuple[bool, Dict[str, Any]]:
    policy = load_policy()
    issues = []
    if not policy.get("enabled", False):
        issues.append("policy_disabled")
    if policy.get("allow_real_hardware") is not True:
        issues.append("allow_real_hardware_false")
    if policy.get("allow_pc_arm") is not True:
        issues.append("allow_pc_arm_false")
    if policy.get("require_manual_arm") is True and confirm != CONFIRM_TEXT:
        issues.append("manual_confirm_missing")
    allowed_profiles = set(policy.get("allowed_profiles_when_armed") or [])
    if allowed_profiles and profile not in allowed_profiles:
        issues.append("profile_not_allowed")
    max_ttl = float(policy.get("max_arm_ttl_s", 300) or 300)
    ttl = max(1.0, min(float(ttl_s or max_ttl), max_ttl))
    allowed = not issues
    result = {
        "ok": True,
        "action": "arm_dry_run" if dry_run else "arm",
        "allowed": allowed,
        "armed": False,
        "profile": profile,
        "ttl_s": ttl,
        "hardware_enabled": False,
        "confirm_required": policy.get("require_manual_arm") is True,
        "issues": issues,
        "reason": "arm_allowed" if allowed else "arm_blocked_by_policy",
    }
    return allowed, result


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(normalized_status(), indent=2, ensure_ascii=False))
    return 0


def cmd_disarm(args: argparse.Namespace) -> int:
    state = load_state()
    state.update({
        "schema_version": 1,
        "armed": False,
        "profile": "pc_dry_run",
        "reason": args.reason or "manual_disarm",
        "armed_until_ts": 0.0,
    })
    save_state(state)
    print(json.dumps({"ok": True, "action": "disarm", "armed": False, "hardware_enabled": False, "state": normalized_status()}, indent=2, ensure_ascii=False))
    return 0


def cmd_arm(args: argparse.Namespace) -> int:
    allowed, result = evaluate_arm_request(args.profile, args.confirm or "", args.ttl_s, args.dry_run)
    if allowed and not args.dry_run:
        until_ts = time.time() + float(result["ttl_s"])
        state = {
            "schema_version": 1,
            "armed": True,
            "profile": args.profile,
            "reason": "manual_arm",
            "armed_until_ts": until_ts,
            "created_by": "robot_arm_control",
        }
        save_state(state)
        result.update({"armed": True, "hardware_enabled": True, "armed_until_ts": until_ts})
    else:
        # Never mutate state for blocked or dry-run arming.
        result["state"] = normalized_status()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (args.dry_run or not allowed) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe robot arm/disarm control")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p_disarm = sub.add_parser("disarm")
    p_disarm.add_argument("--reason", default="manual_disarm")
    p_disarm.set_defaults(func=cmd_disarm)
    p_arm = sub.add_parser("arm")
    p_arm.add_argument("--profile", default="robot_safe_manual")
    p_arm.add_argument("--confirm", default="")
    p_arm.add_argument("--ttl-s", type=float, default=None)
    p_arm.add_argument("--dry-run", action="store_true")
    p_arm.set_defaults(func=cmd_arm)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())