
"""SentryBOT Pi hardware preflight and unified `--doctor` diagnostic tool."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.autonomy.services.pi_hardware_runtime import PiHardwareRuntime  # noqa: E402
from modules.common.model_asset_truth import collect_asset_truth  # noqa: E402


def _read_arm_state(project_root: Path) -> dict[str, Any]:
    arm_path = project_root / ".sentrybot_state" / "arm_state.json"
    if not arm_path.exists():
        return {"exists": False, "path": str(arm_path), "armed": False, "hardware_enabled": False}
    try:
        data = json.loads(arm_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            data = {}
        return {
            "exists": True,
            "path": str(arm_path),
            "armed": bool(data.get("armed", False)),
            "hardware_enabled": bool(data.get("hardware_enabled", False)),
            "profile": data.get("profile"),
            "reason": data.get("reason"),
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(arm_path),
            "armed": False,
            "hardware_enabled": False,
            "error": str(exc),
        }


def _check_systemd_user(project_root: Path) -> dict[str, Any]:
    candidates = [
        Path("/etc/systemd/system/sentrybot.service"),
        project_root / "deploy" / "systemd" / "sentrybot.service",
    ]
    current_user = os.environ.get("SENTRYBOT_SERVICE_USER") or os.environ.get("SUDO_USER") or getpass.getuser()
    service_path: Path | None = None
    for cand in candidates:
        if cand.is_file():
            service_path = cand
            break
    if service_path is None:
        return {
            "found": False,
            "expected_user": current_user,
            "service_user": None,
            "service_group": None,
            "aligned": True,
            "note": "No systemd unit file present to validate.",
        }

    svc_user = None
    svc_group = None
    for line in service_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("User="):
            svc_user = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("Group="):
            svc_group = stripped.split("=", 1)[1].strip()
    aligned = bool(svc_user is None or svc_user == current_user or svc_user == "__SERVICE_USER__")
    return {
        "found": True,
        "path": str(service_path),
        "expected_user": current_user,
        "service_user": svc_user,
        "service_group": svc_group,
        "aligned": aligned,
        "installed_unit": service_path == candidates[0],
    }


def collect_doctor_report(
    project_root: Path,
    *,
    gateway_url: str = "http://127.0.0.1:8080",
) -> dict[str, Any]:
    """Run unified non-invasive diagnostics across Pi runtime, assets, OpenCV, camera lock, arm state, and systemd."""
    from tools.pi_camera_imx500_live_test import check_gateway_camera_lock
    from tools.pi_cv2_package_backend_verification import (
        analyze_cv2_environment,
        collect_cv2_runtime_info,
        collect_installed_opencv_packages,
    )
    from tools.pi_runtime_readiness import collect as collect_readiness
    from tools.pi_v4l2_reversible_camera_probe import build_report as build_camera_probe

    root = project_root.resolve()
    old_cwd = Path.cwd()
    os.chdir(root)
    try:
        runtime_status = PiHardwareRuntime().status()
        assets_status = collect_asset_truth(root)
        readiness_status = collect_readiness()
    finally:
        os.chdir(old_cwd)

    cv2_report = analyze_cv2_environment(
        installed_packages=collect_installed_opencv_packages(),
        cv2_runtime=collect_cv2_runtime_info(),
    )
    arm_state = _read_arm_state(root)
    camera_probe = build_camera_probe(allow_camera_open=False)
    camera_gateway_lock = check_gateway_camera_lock(gateway_url)
    systemd_status = _check_systemd_user(root)

    checks = {
        "runtime_ok": bool(runtime_status.get("ok")),
        "assets_ok": bool(assets_status.get("ok", not assets_status.get("required_missing"))),
        "readiness_ok": bool(readiness_status.get("ok", True)) and not readiness_status.get("missing"),
        "cv2_ok": bool(cv2_report.get("overall_ok")),
        "camera_status_ok": bool(camera_probe.get("overall_ok")) and not bool(camera_gateway_lock.get("capture_running")),
        "arm_safe_disarmed": not bool(arm_state.get("armed")) and not bool(arm_state.get("hardware_enabled")),
        "systemd_user_aligned": bool(systemd_status.get("aligned", True)),
    }
    blockers = [name for name in ("runtime_ok", "assets_ok", "cv2_ok", "camera_status_ok") if not checks[name]]
    warnings = []
    if not checks["readiness_ok"]:
        warnings.append("readiness_items_missing")
    if not checks["arm_safe_disarmed"]:
        warnings.append("robot_arm_currently_armed")
    if not checks["systemd_user_aligned"]:
        warnings.append("systemd_service_user_mismatch")

    overall_ok = not blockers
    summary = {
        "overall_ok": overall_ok,
        "passed_count": sum(1 for v in checks.values() if v),
        "total_checks": len(checks),
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }
    return {
        "ok": overall_ok,
        "doctor": True,
        "project_root": str(root),
        "gateway_url": gateway_url,
        "summary": summary,
        "runtime": runtime_status,
        "assets": assets_status,
        "readiness": readiness_status,
        "cv2": cv2_report,
        "arm_state": arm_state,
        "camera_probe": camera_probe,
        "camera_gateway_lock": camera_gateway_lock,
        "systemd": systemd_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT Pi hardware preflight and --doctor diagnostics.")
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--doctor", action="store_true", help="Run unified diagnostics combining assets, readiness, cv2, camera lock, arm state, and systemd alignment.")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if args.doctor:
        report = collect_doctor_report(root, gateway_url=args.gateway_url)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report.get("ok") else 2

    old = Path.cwd()
    os.chdir(root)
    try:
        status = PiHardwareRuntime().status()
    finally:
        os.chdir(old)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
