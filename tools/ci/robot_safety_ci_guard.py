from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def run_case(name: str, args: list[str], timeout: int = 120) -> tuple[str, str, str]:
    try:
        proc = subprocess.run([PY] + args, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return name, "FAIL", "timeout"
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line for line in reversed(lines) if line.startswith("summary:")), f"exit={proc.returncode}")
    return name, ("PASS" if proc.returncode == 0 else "FAIL"), summary


def main() -> int:
    rows = [
        run_case("companion_ci_guard", ["tools/ci/companion_ci_guard.py"]),
        run_case("capability_matrix", ["tools/robot_capability_probe.py", "matrix"]),
        run_case("robot_safe_manual_gate", ["tools/ci/robot_safe_manual_gate.py"]),
    ]
    print(f"{'case':24} {'status':8} reason")
    print("-" * 78)
    passed = failed = 0
    for name, status, reason in rows:
        print(f"{name:24} {status:8} {reason}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1
    print()
    print(f"summary: {passed}/{passed + failed} passed, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())