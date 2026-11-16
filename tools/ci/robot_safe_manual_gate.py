from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def arm_state() -> tuple[bool, bool]:
    data = read_json(ROOT / ".sentrybot_state" / "arm_state.json", {})
    return bool(data.get("armed", False)), bool(data.get("hardware_enabled", False))


def profile_present() -> bool:
    p = ROOT / "config" / "robot_execution_profiles.json"
    data = read_json(p, {})
    if not isinstance(data, dict) or not data:
        return False
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and any(isinstance(v, dict) and v for v in profiles.values()):
        return True
    return "robot_safe_manual" in json.dumps(data).lower()


def run_capability_matrix() -> tuple[str, str]:
    cmd = [PY, str(ROOT / "tools" / "robot_capability_probe.py"), "matrix"]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=60)
    text = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line for line in reversed(text) if line.startswith("summary:")), f"exit={proc.returncode}")
    return ("PASS" if proc.returncode == 0 else "FAIL"), summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-matrix", action="store_true", help="Skip calling robot_capability_probe.py matrix (for parent guards that run it once).")
    args = ap.parse_args(argv)

    armed, hardware_enabled = arm_state()
    has_profile = profile_present()
    rows = []
    rows.append(("arm_state", "PASS" if not armed and not hardware_enabled else "FAIL", f"armed={armed} hardware_enabled={hardware_enabled}"))
    rows.append(("robot_safe_manual_profile", "PASS" if has_profile else "FAIL", "present" if has_profile else "missing"))
    if not args.skip_matrix:
        st, reason = run_capability_matrix()
        rows.append(("capability_matrix", st, reason))

    print(f"{'case':28} {'status':8} reason")
    print("-" * 86)
    passed = failed = 0
    for name, status, reason in rows:
        print(f"{name:28} {status:8} {reason}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1
    print()
    print(f"summary: {passed}/{passed + failed} passed, failed={failed}, armed={str(armed).lower()}, hardware_enabled={str(hardware_enabled).lower()}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())