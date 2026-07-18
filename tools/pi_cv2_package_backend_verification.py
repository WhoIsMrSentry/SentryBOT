from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

CV2_PACKAGE_BACKEND_VERIFICATION_CONTRACT = True
CV2_PACKAGE_BACKEND_VERIFICATION_ROLE = "pi_cv2_package_backend_report_only_verifier"
CV2_PACKAGE_BACKEND_VERIFICATION_STATUS_ONLY_SAFE = True

OPENCV_PACKAGE_FAMILIES = {
    "opencv-python",
    "opencv-python-headless",
    "opencv-contrib-python",
    "opencv-contrib-python-headless",
}
HEADLESS_FAMILIES = {"opencv-python-headless", "opencv-contrib-python-headless"}
CONTRIB_FAMILIES = {"opencv-contrib-python", "opencv-contrib-python-headless"}


def _norm(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def collect_installed_opencv_packages() -> Dict[str, str]:
    found: Dict[str, str] = {}
    for dist in metadata.distributions():
        name = _norm(dist.metadata.get("Name", ""))
        if name in OPENCV_PACKAGE_FAMILIES:
            found[name] = dist.version
    return dict(sorted(found.items()))


def collect_cv2_runtime_info() -> Dict[str, Any]:
    """Import cv2 for version/build metadata only.

    This function does not open a camera, does not create VideoCapture, and does
    not capture frames.
    """

    try:
        cv2 = importlib.import_module("cv2")
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "cv2_importable": False,
            "cv2_import_error": f"{type(exc).__name__}: {exc}",
            "cv2_version": None,
            "v4l2_build_support": None,
            "build_info_checked": False,
        }

    version = getattr(cv2, "__version__", None)
    build_info = ""
    try:
        build_info = str(cv2.getBuildInformation())
    except Exception:
        build_info = ""

    return {
        "cv2_importable": True,
        "cv2_import_error": None,
        "cv2_version": version,
        "v4l2_build_support": detect_v4l2_support(build_info),
        "build_info_checked": bool(build_info),
    }


def detect_v4l2_support(build_info: str) -> Optional[bool]:
    text = str(build_info or "").lower()
    if "v4l/v4l2" in text or "v4l2" in text:
        if "yes" in text or "true" in text or "enabled" in text:
            return True
        if "no" in text or "false" in text or "disabled" in text:
            return False
    return None


def is_pi_linux(system_name: str, machine: str) -> bool:
    sys_name = str(system_name or "").lower()
    mach = str(machine or "").lower()
    return sys_name == "linux" and any(token in mach for token in ("aarch64", "armv7", "armv6", "arm64"))


def analyze_cv2_environment(
    *,
    installed_packages: Mapping[str, str],
    cv2_runtime: Optional[Mapping[str, Any]] = None,
    platform_system: Optional[str] = None,
    platform_machine: Optional[str] = None,
    target_pi: Optional[bool] = None,
) -> Dict[str, Any]:
    packages = {_norm(k): str(v) for k, v in dict(installed_packages or {}).items()}
    runtime = dict(cv2_runtime or {})
    system_name = platform_system if platform_system is not None else platform.system()
    machine = platform_machine if platform_machine is not None else platform.machine()
    pi_target = bool(target_pi) if target_pi is not None else is_pi_linux(system_name, machine)

    package_names = sorted(name for name in packages if name in OPENCV_PACKAGE_FAMILIES)
    headless_packages = [name for name in package_names if name in HEADLESS_FAMILIES]
    contrib_packages = [name for name in package_names if name in CONTRIB_FAMILIES]

    warnings = []
    blockers = []

    if len(package_names) == 0:
        warnings.append("no_opencv_wheel_package_detected")
    elif len(package_names) > 1:
        blockers.append("multiple_cv2_namespace_packages_detected")

    if pi_target and len(package_names) == 1 and package_names[0] not in HEADLESS_FAMILIES:
        blockers.append("pi_target_should_use_headless_package")

    if runtime.get("cv2_importable") is False:
        warnings.append("cv2_not_importable")

    if pi_target and runtime.get("v4l2_build_support") is not True:
        warnings.append("pi_v4l2_build_support_not_confirmed")

    recommended_package = "opencv-python-headless"
    if contrib_packages:
        recommended_package = "opencv-contrib-python-headless"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "contract": {
            "CV2_PACKAGE_BACKEND_VERIFICATION_CONTRACT": CV2_PACKAGE_BACKEND_VERIFICATION_CONTRACT,
            "role": CV2_PACKAGE_BACKEND_VERIFICATION_ROLE,
            "status_only_safe": CV2_PACKAGE_BACKEND_VERIFICATION_STATUS_ONLY_SAFE,
        },
        "target": {
            "platform_system": system_name,
            "platform_machine": machine,
            "target_pi": pi_target,
            "preferred_capture_backend": "Linux V4L2" if pi_target else "host_default_status_only",
        },
        "packages": {
            "opencv_package_families_detected": package_names,
            "package_versions": {name: packages[name] for name in package_names},
            "package_count": len(package_names),
            "single_cv2_namespace_package": len(package_names) == 1,
            "headless_package_detected": bool(headless_packages),
            "contrib_package_detected": bool(contrib_packages),
            "recommended_package_family": recommended_package,
        },
        "cv2_runtime": runtime,
        "warnings": warnings,
        "blockers": blockers,
        "overall_ok": not blockers,
        "activation_allowed_now": False,
        "safety": {
            "camera_started": False,
            "frame_captured": False,
            "vlm_inference_started": False,
            "network_called": False,
            "ollama_called": False,
            "hardware_enabled": False,
            "motion_started": False,
            "audio_started": False,
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    packages = report["packages"]
    target = report["target"]
    runtime = report["cv2_runtime"]
    lines = [
        "# SentryBOT Pi cv2 Package/Backend Verification",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "This is report-only. It does not open a camera, capture a frame, run VLM inference, call Ollama/network services, or enable hardware.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| overall_ok | {report['overall_ok']} |",
        f"| activation_allowed_now | {report['activation_allowed_now']} |",
        f"| target_pi | {target['target_pi']} |",
        f"| platform | {target['platform_system']} {target['platform_machine']} |",
        f"| preferred_capture_backend | {target['preferred_capture_backend']} |",
        f"| opencv_package_count | {packages['package_count']} |",
        f"| single_cv2_namespace_package | {packages['single_cv2_namespace_package']} |",
        f"| headless_package_detected | {packages['headless_package_detected']} |",
        f"| recommended_package_family | {packages['recommended_package_family']} |",
        f"| cv2_importable | {runtime.get('cv2_importable')} |",
        f"| cv2_version | {runtime.get('cv2_version')} |",
        f"| v4l2_build_support | {runtime.get('v4l2_build_support')} |",
        "",
        "## Detected OpenCV packages",
        "",
    ]

    if packages["package_versions"]:
        lines.extend(["| package | version |", "| --- | --- |"])
        for name, version in packages["package_versions"].items():
            lines.append(f"| {name} | {version} |")
    else:
        lines.append("- None detected through package metadata.")

    lines += [
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])

    lines += [
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- None"])

    lines += [
        "",
        "## Safety state",
        "",
        "```text",
    ]
    for key, value in report["safety"].items():
        lines.append(f"{key}={value}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report-only Pi cv2 package/backend verification.")
    parser.add_argument("--json-out", default="pi_cv2_package_backend_verification.json")
    parser.add_argument("--md-out", default="PI_CV2_PACKAGE_BACKEND_VERIFICATION.md")
    parser.add_argument("--target-pi", action="store_true", help="Treat current environment as target Pi for policy checks.")
    parser.add_argument("--require-pi-strict", action="store_true", help="Exit non-zero if Pi policy blockers exist.")
    args = parser.parse_args()

    report = analyze_cv2_environment(
        installed_packages=collect_installed_opencv_packages(),
        cv2_runtime=collect_cv2_runtime_info(),
        target_pi=args.target_pi or None,
    )

    Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(report), encoding="utf-8")

    print(f"[WRITE] {args.md_out}")
    print(f"[WRITE] {args.json_out}")
    print(f"[SUMMARY] overall_ok={report['overall_ok']}")
    print(f"[SUMMARY] activation_allowed_now={report['activation_allowed_now']}")
    print(f"[SUMMARY] target_pi={report['target']['target_pi']}")
    print(f"[SUMMARY] package_count={report['packages']['package_count']}")
    print(f"[SUMMARY] headless_package_detected={report['packages']['headless_package_detected']}")
    print(f"[SUMMARY] cv2_importable={report['cv2_runtime'].get('cv2_importable')}")
    print(f"[SUMMARY] cv2_version={report['cv2_runtime'].get('cv2_version')}")
    print("[SUMMARY] camera_started=False")
    print("[SUMMARY] frame_captured=False")
    print("[SUMMARY] hardware_enabled=False")

    if args.require_pi_strict and report["blockers"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
