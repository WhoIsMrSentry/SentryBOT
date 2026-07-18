from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def read_arm() -> tuple[bool, bool, str]:
    p = ROOT / ".sentrybot_state" / "arm_state.json"
    if not p.exists():
        return False, False, "missing_defaults_disarmed"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, False, f"read_error:{exc}"
    return bool(data.get("armed", False)), bool(data.get("hardware_enabled", False)), "ok"


def main() -> int:
    armed, hardware_enabled, arm_reason = read_arm()
    rows = [
        ("modules_present", "PASS" if exists("modules") else "FAIL", "modules/"),
        ("apps_present", "PASS" if exists("apps/run_robot_tui.py") else "FAIL", "apps/run_robot_tui.py"),
        ("config_present", "PASS" if exists("config") else "FAIL", "config/"),
        ("arm_state_disarmed", "PASS" if not armed and not hardware_enabled else "FAIL", f"armed={armed} hardware_enabled={hardware_enabled} {arm_reason}"),
        ("safety_tools_present", "PASS" if exists("tools/robot_capability_probe.py") and exists("tools/ci/robot_safe_manual_gate.py") else "FAIL", "robot-only safety tools"),
        ("world_memory_optional", "PASS", "runtime state may be created later"),
    ]
    print(f"{'case':28} {'status':8} reason")
    print("-" * 86)
    passed = 0
    failed = 0
    for name, status, reason in rows:
        print(f"{name:28} {status:8} {reason}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1
    print()
    print(f"summary: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())