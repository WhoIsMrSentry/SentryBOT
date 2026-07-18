from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
BASE_URL = "http://127.0.0.1:8080"

ENDPOINTS = [
    ("goal_execution", "/autonomy/goal/execution", True, "runtime"),
    ("behavior_loop", "/autonomy/behavior-loop", True, "runtime"),
    ("expression_output", "/expression/output/status", True, "runtime"),
    ("world_memory", "/autonomy/memory", True, "runtime"),
    ("camera", "/camera/status", True, "robot_hardware"),
    ("speech", "/speech/status", False, "pc_optional"),
    ("tts", "/tts/status", True, "robot_hardware"),
    ("arduino", "/arduino/status", True, "robot_hardware"),
]


def read_json_file(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def arm_state() -> tuple[bool, bool]:
    data = read_json_file(ROOT / ".sentrybot_state" / "arm_state.json", {})
    return bool(data.get("armed", False)), bool(data.get("hardware_enabled", False))


def run_tool(args: list[str], timeout: int = 90) -> tuple[str, str]:
    try:
        proc = subprocess.run([PY] + args, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "FAIL", "timeout"
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line for line in reversed(lines) if line.startswith("summary:")), f"exit={proc.returncode}")
    return ("PASS" if proc.returncode == 0 else "FAIL"), summary


def fetch(path: str, timeout: float = 2.0) -> tuple[bool, Any, str]:
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            return True, json.loads(raw), "ok"
        except Exception:
            return True, {"raw": raw}, "non_json"
    except urllib.error.HTTPError as exc:
        return False, None, f"HTTPError: HTTP Error {exc.code}: {exc.reason}"
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def classify_endpoint(name: str, path: str, required_robot: bool, kind: str) -> tuple[str, str]:
    ok, data, reason = fetch(path)
    if not ok:
        if kind == "robot_hardware":
            return "NEEDED_BEFORE_ROBOT", reason
        return "PC", reason
    if not isinstance(data, dict):
        return "PC", "endpoint returned non-object"

    if name == "speech":
        model_ready = bool(data.get("model_ready", False))
        stt_available = bool(data.get("stt_available", False))
        if not model_ready or not stt_available or not bool(data.get("ok", False)):
            return "PC", f"ok={data.get('ok')} model_ready={model_ready} stt_available={stt_available}"
        return "READY", "speech ready"

    if name == "arduino":
        controller_ready = bool(data.get("controller_ready", False))
        connected = bool(data.get("connected", False))
        if controller_ready and connected:
            return "READY", f"controller_ready=True connected=True reason={data.get('reason','')}"
        return "NEEDED_BEFORE_ROBOT", f"endpoint_ok controller_ready={controller_ready} connected={connected} reason={data.get('reason','')} ports={data.get('serial_port_count', data.get('ports', 0))}"

    if name in {"camera", "tts"}:
        if bool(data.get("ok", False)) and bool(data.get("available", data.get("ready", False))):
            return "READY", "ok=True available=True"
        return "NEEDED_BEFORE_ROBOT", f"endpoint_ok ok={data.get('ok')} available={data.get('available', data.get('ready', False))}"

    return "READY", "endpoint reachable"


def status(require_robot_hardware: bool = False) -> int:
    armed, hardware_enabled = arm_state()
    safety_rows = []
    safety_rows.append(("arm_state", "PASS" if not armed and not hardware_enabled else "FAIL", f"armed={armed} hardware_enabled={hardware_enabled}"))
    safety_rows.append(("baseline_required", "PASS", "disabled_robot_only_live_checks"))
    st, reason = run_tool(["tools/robot_capability_probe.py", "matrix"])
    safety_rows.append(("capability_matrix", st, reason))
    st, reason = run_tool(["tools/ci/robot_safe_manual_gate.py"])
    safety_rows.append(("robot_safe_manual_gate", st, reason))

    inventory = []
    for item in ENDPOINTS:
        name, path, required, kind = item
        st, reason = classify_endpoint(name, path, required, kind)
        inventory.append((name, st, required, reason))

    print("Safety locks")
    print(f"{'case':26} {'status':8} reason")
    print("-" * 104)
    safety_failures = 0
    for name, st, reason in safety_rows:
        print(f"{name:26} {st:8} {reason}")
        if st != "PASS":
            safety_failures += 1

    print()
    print("Hardware/runtime inventory")
    print(f"{'component':18} {'status':21} {'required_robot':15} reason")
    print("-" * 138)
    ready = pc_or_needed = robot_blockers = 0
    for name, st, required, reason in inventory:
        print(f"{name:18} {st:21} {str(required):15} {reason}")
        if st == "READY":
            ready += 1
        else:
            pc_or_needed += 1
        if required and st == "NEEDED_BEFORE_ROBOT" and name in {"camera", "tts", "arduino"}:
            robot_blockers += 1

    overall_ok = safety_failures == 0 and (not require_robot_hardware or robot_blockers == 0)
    print()
    print(f"summary: ok={str(overall_ok)}, armed={armed}, hardware_enabled={hardware_enabled}, ready={ready}, pc_or_needed={pc_or_needed}, robot_blockers={robot_blockers}, baseline_required=False")
    return 0 if overall_ok else 1


def main() -> int:
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    require = "--require-robot-hardware" in sys.argv
    if cmd == "status":
        return status(require)
    if cmd == "json":
        code = status(require)
        return code
    print("usage: robot_hardware_gap_report.py status [--require-robot-hardware]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())