from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def _parse_env_keys(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = val.strip()
    return values


def check_env_example_consistency(root: Path = ROOT) -> tuple[bool, str]:
    """Verify `.env.example` and `deploy/systemd/sentrybot.env.example` share required keys & valid profile."""
    local_env = _parse_env_keys(root / ".env.example")
    systemd_env = _parse_env_keys(root / "deploy" / "systemd" / "sentrybot.env.example")
    if not local_env:
        return False, ".env.example missing or empty"
    if not systemd_env:
        return False, "deploy/systemd/sentrybot.env.example missing or empty"
    missing_in_systemd = sorted(k for k in local_env if k not in systemd_env)
    if missing_in_systemd:
        return False, f"missing in systemd.env.example: {', '.join(missing_in_systemd)}"
    profile = systemd_env.get("SENTRYBOT_PROFILE", "")
    if profile not in {"pc", "pc-test", "robot"}:
        return False, f"invalid SENTRYBOT_PROFILE={profile!r} (expected pc|pc-test|robot)"
    return True, f"keys={len(systemd_env)} SENTRYBOT_PROFILE={profile}"


def run_case(name: str, args: list[str], timeout: int = 120) -> tuple[str, str, str]:
    try:
        proc = subprocess.run([PY] + args, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return name, "FAIL", "timeout"
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line for line in reversed(lines) if line.startswith("summary:")), f"exit={proc.returncode}")
    return name, ("PASS" if proc.returncode == 0 else "FAIL"), summary


def main(argv: list[str] | None = None) -> int:
    skip_tests = "--skip-tests" in (argv if argv is not None else sys.argv[1:])
    ci_guard_args = ["tools/ci/companion_ci_guard.py"]
    if skip_tests or os.environ.get("PYTEST_CURRENT_TEST"):
        ci_guard_args.append("--skip-tests")

    rows = [
        run_case("companion_ci_guard", ci_guard_args),
        run_case("capability_matrix", ["tools/robot_capability_probe.py", "matrix"]),
        run_case("robot_safe_manual_gate", ["tools/ci/robot_safe_manual_gate.py", "--skip-matrix"]),
    ]
    env_ok, env_reason = check_env_example_consistency(ROOT)
    rows.append(("env_example_consistency", "PASS" if env_ok else "FAIL", env_reason))
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