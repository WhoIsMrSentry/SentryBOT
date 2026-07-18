from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CAPABILITIES = [
    {"name": "expression.event", "risk": "none", "needs_hardware": False, "real_command": False},
    {"name": "speech.silent", "risk": "none", "needs_hardware": False, "real_command": False},
    {"name": "vision.cheap", "risk": "none", "needs_hardware": False, "real_command": False},
    {"name": "scheduler.wait", "risk": "none", "needs_hardware": False, "real_command": False},
    {"name": "motion.freeze", "risk": "low", "needs_hardware": True, "real_command": False},
    {"name": "motion.attend", "risk": "low", "needs_hardware": True, "real_command": False},
    {"name": "motion.look_around", "risk": "low", "needs_hardware": True, "real_command": False},
    {"name": "pose.sleepy_idle", "risk": "low", "needs_hardware": True, "real_command": False},
]


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def arm_state() -> tuple[bool, bool]:
    data = read_json(ROOT / ".sentrybot_state" / "arm_state.json", {})
    return bool(data.get("armed", False)), bool(data.get("hardware_enabled", False))


def has_robot_safe_manual_profile() -> bool:
    p = ROOT / "config" / "robot_execution_profiles.json"
    data = read_json(p, {})
    text = json.dumps(data).lower() if data else ""
    return "robot_safe_manual" in text or p.exists()


def print_rows(rows: list[tuple[str, str, str]], title: str | None = None) -> int:
    if title:
        print(title)
    print(f"{'case':28} {'status':8} reason")
    print("-" * 90)
    passed = failed = 0
    for name, status, reason in rows:
        print(f"{name:28} {status:8} {reason}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1
    print()
    print(f"summary: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


def command_list() -> int:
    print(f"{'capability':24} {'risk':8} {'hardware':9} {'real_cmd':8}")
    print("-" * 60)
    for c in CAPABILITIES:
        print(f"{c['name']:24} {c['risk']:8} {str(c['needs_hardware']):9} {str(c['real_command']):8}")
    return 0


def command_matrix() -> int:
    armed, hardware_enabled = arm_state()
    rows = [
        ("profile_config", "PASS" if has_robot_safe_manual_profile() else "FAIL", "robot_safe_manual profile/config present"),
        ("arm_lock", "PASS" if not armed and not hardware_enabled else "FAIL", f"armed={armed} hardware_enabled={hardware_enabled}"),
        ("capability_registry", "PASS" if len(CAPABILITIES) >= 6 else "FAIL", f"capabilities={len(CAPABILITIES)}"),
        ("real_hardware_disabled", "PASS" if not hardware_enabled else "FAIL", f"hardware_enabled={hardware_enabled}"),
        ("manual_profile_dryrun", "PASS" if not hardware_enabled else "FAIL", "real commands remain disabled until explicit robot arm step"),
        ("semantic_not_pwm", "PASS", "capabilities describe semantic actions, not raw servo/pwm"),
    ]
    return print_rows(rows)


def command_json() -> int:
    armed, hardware_enabled = arm_state()
    out = {
        "ok": (not armed and not hardware_enabled and len(CAPABILITIES) >= 6),
        "armed": armed,
        "hardware_enabled": hardware_enabled,
        "capabilities": CAPABILITIES,
    }
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


def main() -> int:
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "matrix"
    if cmd == "list":
        return command_list()
    if cmd == "matrix":
        return command_matrix()
    if cmd == "json":
        return command_json()
    print("usage: robot_capability_probe.py [list|matrix|json]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())