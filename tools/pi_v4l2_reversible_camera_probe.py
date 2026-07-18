from __future__ import annotations

import argparse
import importlib
import json
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

V4L2_REVERSIBLE_CAMERA_PROBE_CONTRACT = True
V4L2_REVERSIBLE_CAMERA_PROBE_ROLE = "explicit_opt_in_reversible_v4l2_probe"
V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_STATUS_ONLY_SAFE = True
V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_ALLOWS_CAMERA_OPEN = False


@dataclass(frozen=True)
class CameraProbeDecision:
    device: Optional[str]
    allow_camera_open: bool
    camera_open_attempted: bool
    camera_opened: bool
    released: bool
    frame_captured: bool
    reason: str
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "allow_camera_open": self.allow_camera_open,
            "camera_open_attempted": self.camera_open_attempted,
            "camera_opened": self.camera_opened,
            "released": self.released,
            "frame_captured": self.frame_captured,
            "reason": self.reason,
            "error": self.error,
        }


def is_pi_linux(system_name: Optional[str] = None, machine: Optional[str] = None) -> bool:
    sys_name = str(system_name if system_name is not None else platform.system()).lower()
    mach = str(machine if machine is not None else platform.machine()).lower()
    return sys_name == "linux" and any(token in mach for token in ("aarch64", "armv7", "armv6", "arm64"))


def discover_video_devices(dev_root: str | Path = "/dev") -> List[str]:
    root = Path(dev_root)
    if not root.exists():
        return []
    devices = []
    for path in root.glob("video*"):
        suffix = path.name.removeprefix("video")
        if suffix.isdigit():
            devices.append(str(path))
    return sorted(devices)


def _load_cv2() -> Any:
    return importlib.import_module("cv2")


def probe_device(
    device: str | Path,
    *,
    allow_camera_open: bool = False,
    backend: str = "v4l2",
    cv2_module: Any = None,
) -> CameraProbeDecision:
    dev = str(device)

    if not allow_camera_open:
        return CameraProbeDecision(
            device=dev,
            allow_camera_open=False,
            camera_open_attempted=False,
            camera_opened=False,
            released=False,
            frame_captured=False,
            reason="camera_open_not_allowed_default_status_only",
        )

    cap = None
    opened = False
    released = False
    try:
        cv2 = cv2_module if cv2_module is not None else _load_cv2()
        backend_id = getattr(cv2, "CAP_V4L2", 200) if backend.lower() == "v4l2" else 0
        cap = cv2.VideoCapture(dev, backend_id)
        opened = bool(cap.isOpened()) if hasattr(cap, "isOpened") else False
        return CameraProbeDecision(
            device=dev,
            allow_camera_open=True,
            camera_open_attempted=True,
            camera_opened=opened,
            released=False,
            frame_captured=False,
            reason="opened_and_released" if opened else "open_failed",
        )
    except Exception as exc:
        return CameraProbeDecision(
            device=dev,
            allow_camera_open=True,
            camera_open_attempted=True,
            camera_opened=False,
            released=False,
            frame_captured=False,
            reason="open_exception",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if cap is not None and hasattr(cap, "release"):
            try:
                cap.release()
                released = True
            except Exception:
                released = False
            if opened:
                object.__setattr__(
                    locals().get("_dummy", CameraProbeDecision(dev, True, True, opened, released, False, "")),
                    "released",
                    released,
                )


def probe_device_reversible(
    device: str | Path,
    *,
    allow_camera_open: bool = False,
    backend: str = "v4l2",
    cv2_module: Any = None,
) -> CameraProbeDecision:
    """Probe wrapper with guaranteed release state in the returned decision."""

    dev = str(device)
    if not allow_camera_open:
        return probe_device(dev, allow_camera_open=False, backend=backend, cv2_module=cv2_module)

    cap = None
    opened = False
    released = False
    error = None
    reason = "open_failed"
    try:
        cv2 = cv2_module if cv2_module is not None else _load_cv2()
        backend_id = getattr(cv2, "CAP_V4L2", 200) if backend.lower() == "v4l2" else 0
        cap = cv2.VideoCapture(dev, backend_id)
        opened = bool(cap.isOpened()) if hasattr(cap, "isOpened") else False
        reason = "opened_and_released" if opened else "open_failed"
    except Exception as exc:
        reason = "open_exception"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if cap is not None and hasattr(cap, "release"):
            try:
                cap.release()
                released = True
            except Exception as exc:
                released = False
                error = error or f"{type(exc).__name__}: {exc}"
    return CameraProbeDecision(
        device=dev,
        allow_camera_open=True,
        camera_open_attempted=True,
        camera_opened=opened,
        released=released,
        frame_captured=False,
        reason=reason,
        error=error,
    )


def build_report(
    *,
    allow_camera_open: bool = False,
    target_pi: Optional[bool] = None,
    device: Optional[str] = None,
    dev_root: str | Path = "/dev",
) -> Dict[str, Any]:
    devices = discover_video_devices(dev_root)
    selected_device = device or (devices[0] if devices else None)
    pi_target = bool(target_pi) if target_pi is not None else is_pi_linux()

    if selected_device is None:
        decision = CameraProbeDecision(
            device=None,
            allow_camera_open=allow_camera_open,
            camera_open_attempted=False,
            camera_opened=False,
            released=False,
            frame_captured=False,
            reason="no_video_device_found",
        )
    else:
        decision = probe_device_reversible(selected_device, allow_camera_open=allow_camera_open)

    warnings = []
    blockers = []
    if pi_target and not devices:
        warnings.append("no_dev_video_devices_found")
    if allow_camera_open and not pi_target:
        warnings.append("camera_open_requested_on_non_pi_host")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "contract": {
            "V4L2_REVERSIBLE_CAMERA_PROBE_CONTRACT": V4L2_REVERSIBLE_CAMERA_PROBE_CONTRACT,
            "role": V4L2_REVERSIBLE_CAMERA_PROBE_ROLE,
            "default_status_only_safe": V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_STATUS_ONLY_SAFE,
            "default_allows_camera_open": V4L2_REVERSIBLE_CAMERA_PROBE_DEFAULT_ALLOWS_CAMERA_OPEN,
        },
        "target": {
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
            "target_pi": pi_target,
            "preferred_capture_backend": "Linux V4L2" if pi_target else "host_default_status_only",
        },
        "devices": {
            "dev_root": str(dev_root),
            "video_devices": devices,
            "selected_device": selected_device,
        },
        "probe": decision.as_dict(),
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
    probe = report["probe"]
    target = report["target"]
    devices = report["devices"]
    lines = [
        "# SentryBOT Pi V4L2 Reversible Camera Probe",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "Default mode is status-only. It does not open a camera, capture a frame, run VLM inference, call Ollama/network services, or enable hardware.",
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
        f"| video_device_count | {len(devices['video_devices'])} |",
        f"| selected_device | {devices['selected_device']} |",
        f"| allow_camera_open | {probe['allow_camera_open']} |",
        f"| camera_open_attempted | {probe['camera_open_attempted']} |",
        f"| camera_opened | {probe['camera_opened']} |",
        f"| released | {probe['released']} |",
        f"| frame_captured | {probe['frame_captured']} |",
        f"| reason | {probe['reason']} |",
        "",
        "## Detected devices",
        "",
    ]
    lines.extend([f"- {item}" for item in devices["video_devices"]] or ["- None"])
    lines += ["", "## Warnings", ""]
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])
    lines += ["", "## Blockers", ""]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- None"])
    lines += ["", "## Safety state", "", "```text"]
    for key, value in report["safety"].items():
        lines.append(f"{key}={value}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report-only reversible V4L2 camera probe.")
    parser.add_argument("--json-out", default="pi_v4l2_reversible_camera_probe.json")
    parser.add_argument("--md-out", default="PI_V4L2_REVERSIBLE_CAMERA_PROBE.md")
    parser.add_argument("--dev-root", default="/dev")
    parser.add_argument("--device", default=None)
    parser.add_argument("--target-pi", action="store_true")
    parser.add_argument("--allow-camera-open", action="store_true", help="Explicit opt-in: open then immediately release selected camera. Does not read frames.")
    args = parser.parse_args()

    report = build_report(
        allow_camera_open=bool(args.allow_camera_open),
        target_pi=args.target_pi or None,
        device=args.device,
        dev_root=args.dev_root,
    )
    Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(report), encoding="utf-8")

    print(f"[WRITE] {args.md_out}")
    print(f"[WRITE] {args.json_out}")
    print(f"[SUMMARY] overall_ok={report['overall_ok']}")
    print(f"[SUMMARY] activation_allowed_now={report['activation_allowed_now']}")
    print(f"[SUMMARY] target_pi={report['target']['target_pi']}")
    print(f"[SUMMARY] video_device_count={len(report['devices']['video_devices'])}")
    print(f"[SUMMARY] allow_camera_open={report['probe']['allow_camera_open']}")
    print(f"[SUMMARY] camera_open_attempted={report['probe']['camera_open_attempted']}")
    print(f"[SUMMARY] camera_opened={report['probe']['camera_opened']}")
    print(f"[SUMMARY] released={report['probe']['released']}")
    print("[SUMMARY] frame_captured=False")
    print("[SUMMARY] hardware_enabled=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
