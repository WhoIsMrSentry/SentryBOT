from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
OUT_MD = ROOT / "ROBOT_RUNTIME_GATEWAY_STATUS_REPORT.md"
OUT_JSON = ROOT / "robot_runtime_gateway_status_report.json"

SAFE_GET_ENDPOINTS = [
    "/healthz",
    "/status",
    "/health",
    "/camera/status",
    "/camera/healthz",
    "/camera/onsensor/latest",
    "/vlm/status",
    "/vlm/healthz",
    "/vlm/context/latest",
    "/vlm/results/latest",
    "/autonomy/state",
    "/autonomy/needs",
    "/autonomy/vision-context",
    "/autonomy/goal/execution",
    "/expression/status",
    "/expression/output/status",
    "/speech/status",
    "/speak/status",
    "/wakeword/status",
]

FORBIDDEN_ENDPOINTS = [
    "/camera/start",
    "/camera/snap",
    "/camera/video",
    "/vlm/query",
    "/vlm/track",
    "/autonomy/goal/execute",
    "/autonomy/goal/auto/tick",
    "/arduino/request",
    "/piservo",
    "/neopixel",
]

CONFIG_FILES = [
    "config/robot_execution_profiles.json",
    "config/robot_capability_registry.json",
    "config/robot_arm_policy.json",
    "modules/camera/config/config.yml",
    "modules/vlm_bridge/config/config.yml",
    "modules/speak/config/config.yml",
    "modules/speech/config/config.yml",
    "modules/wakeword/config/config.yml",
    "companion_roadmap_checkpoint.json",
    "robot_capability_source_contract.json",
]

RUNTIME_FILES = [
    "modules/autonomy/services/robot_capability_map.py",
    "modules/autonomy/services/companion_goal_executor.py",
    "modules/autonomy/services/companion_auto_execute_gate.py",
    "modules/camera/api/router.py",
    "modules/camera/services/capture.py",
    "modules/vlm_bridge/services/processor.py",
    "modules/gateway/services/bootstrap.py",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def safe_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except Exception as exc:
        return {"_error": str(exc)}


def safe_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        return {"_yaml_available": False, "_error": str(exc)}
    try:
        return yaml.safe_load(read_text(path))
    except Exception as exc:
        return {"_yaml_available": True, "_error": str(exc)}


def summarize(value: Any, depth: int = 0) -> Any:
    if depth > 2:
        return "..."
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:60]:
            if isinstance(item, dict):
                out[str(key)] = {"type": "object", "keys": list(item.keys())[:24], "count": len(item)}
            elif isinstance(item, list):
                out[str(key)] = {"type": "list", "count": len(item)}
            else:
                out[str(key)] = item
        return out
    if isinstance(value, list):
        return {"type": "list", "count": len(value), "sample": value[:5]}
    return value


def detect_platform() -> dict[str, Any]:
    info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "hostname": socket.gethostname(),
        "is_linux": platform.system().lower() == "linux",
        "is_windows": platform.system().lower() == "windows",
        "is_robot_like": False,
        "model": None,
    }
    model_paths = [
        Path("/proc/device-tree/model"),
        Path("/sys/firmware/devicetree/base/model"),
        Path("/proc/cpuinfo"),
    ]
    for path in model_paths:
        if not path.exists():
            continue
        try:
            text = read_text(path).replace("\x00", "").strip()
            if path.name == "cpuinfo":
                for line in text.splitlines():
                    if line.lower().startswith(("model", "hardware", "revision")):
                        info.setdefault("cpuinfo_lines", []).append(line.strip())
                continue
            info["model"] = text[:300]
            break
        except Exception:
            pass
    machine = str(info.get("machine") or "").lower()
    model = str(info.get("model") or "").lower()
    info["is_robot_like"] = bool(info["is_linux"] and (
        "arm" in machine or "aarch64" in machine or "raspberry" in model or "radxa" in model or "orangepi" in model
    ))
    return info


def linux_devices() -> dict[str, Any]:
    if platform.system().lower() != "linux":
        return {"available": False, "reason": "not_linux_robot_target"}
    video = sorted(glob.glob("/dev/video*"))
    tty = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/serial/by-id/*"))
    i2c = sorted(glob.glob("/dev/i2c-*"))
    gpio = sorted(glob.glob("/dev/gpiochip*"))
    video_names = []
    for v4l in sorted(Path("/sys/class/video4linux").glob("*")) if Path("/sys/class/video4linux").exists() else []:
        name_path = v4l / "name"
        try:
            video_names.append({"node": "/dev/" + v4l.name, "name": read_text(name_path).strip()})
        except Exception:
            video_names.append({"node": "/dev/" + v4l.name, "name": None})
    return {
        "available": True,
        "video": video,
        "video_names": video_names,
        "serial": tty,
        "i2c": i2c,
        "gpio": gpio,
    }


def cv2_status() -> dict[str, Any]:
    out: dict[str, Any] = {"importable": False, "note": "No VideoCapture opened."}
    try:
        import cv2  # type: ignore
        out["importable"] = True
        out["version"] = getattr(cv2, "__version__", None)
        out["has_video_capture"] = hasattr(cv2, "VideoCapture")
        out["has_videoio_registry"] = hasattr(cv2, "videoio_registry")
        if hasattr(cv2, "videoio_registry"):
            backends = []
            try:
                for backend in cv2.videoio_registry.getBackends():
                    try:
                        name = cv2.videoio_registry.getBackendName(backend)
                    except Exception:
                        name = str(backend)
                    backends.append({"id": int(backend), "name": name})
            except Exception as exc:
                out["backend_error"] = str(exc)
                backends = []
            out["videoio_backends"] = backends
    except Exception as exc:
        out["error"] = str(exc)
    return out


def safe_get(base_url: str, endpoint: str, timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + endpoint
    start = time.time()
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json,text/plain,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(8000)
            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return {
                "endpoint": endpoint,
                "ok": True,
                "status": resp.status,
                "elapsed_ms": round((time.time() - start) * 1000, 1),
                "content_type": resp.headers.get("content-type"),
                "json": parsed,
                "text_preview": text[:1000],
            }
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read(2000).decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {
            "endpoint": endpoint,
            "ok": False,
            "http_status": exc.code,
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "error": str(exc),
            "text_preview": text[:1000],
        }
    except Exception as exc:
        return {
            "endpoint": endpoint,
            "ok": False,
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "error": str(exc),
        }


def config_summary() -> list[dict[str, Any]]:
    rows = []
    for name in CONFIG_FILES:
        path = ROOT / name
        item: dict[str, Any] = {"path": name, "exists": path.exists()}
        if path.exists():
            item["lines"] = read_text(path).count("\n") + 1
            if path.suffix.lower() == ".json":
                item["summary"] = summarize(safe_json(path))
            elif path.suffix.lower() in {".yml", ".yaml"}:
                item["summary"] = summarize(safe_yaml(path))
        rows.append(item)
    return rows


def file_summary() -> list[dict[str, Any]]:
    rows = []
    for name in RUNTIME_FILES:
        path = ROOT / name
        item: dict[str, Any] = {"path": name, "exists": path.exists()}
        if path.exists():
            text = read_text(path)
            item["lines"] = text.count("\n") + 1
            item["robot_terms"] = sorted({term for term in [
                "hardware_enabled", "armed", "dry_run", "robot_safe", "capability",
                "camera", "vlm", "start", "status", "health", "execute"
            ] if term in text})
        rows.append(item)
    return rows


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>")[:500] for x in row) + " |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Robot-first SentryBOT gateway status probe. Status-only; no camera/hardware start.")
    parser.add_argument("--gateway-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--start-gateway-cmd", default="", help="Optional explicit command. Not used unless supplied.")
    parser.add_argument("--start-wait-s", type=float, default=8.0)
    args = parser.parse_args()

    platform_info = detect_platform()
    devices = linux_devices()
    cv2 = cv2_status()
    configs = config_summary()
    files = file_summary()

    started_process = None
    started_command = None
    start_error = None

    if args.start_gateway_cmd.strip():
        # Explicit only. We still force safe status semantics by default.
        env = os.environ.copy()
        env.setdefault("SENTRYBOT_DISABLE_AUTOSTART", "true")
        env.setdefault("SENTRYBOT_ROBOT_STATUS_PROBE", "1")
        started_command = args.start_gateway_cmd
        try:
            started_process = subprocess.Popen(
                args.start_gateway_cmd,
                cwd=str(ROOT),
                shell=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(max(0.2, args.start_wait_s))
        except Exception as exc:
            start_error = str(exc)

    http_results = [safe_get(args.gateway_base_url, endpoint, args.timeout) for endpoint in SAFE_GET_ENDPOINTS]
    gateway_reachable = any(r.get("ok") or r.get("http_status") for r in http_results)

    if started_process is not None:
        try:
            started_process.terminate()
            try:
                started_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                started_process.kill()
        except Exception:
            pass

    blockers = []
    warnings = []

    if not any(row["path"] == "config/robot_capability_registry.json" and row["exists"] for row in configs):
        blockers.append("capability_registry_missing")
    if not any(row["path"] == "config/robot_execution_profiles.json" and row["exists"] for row in configs):
        blockers.append("robot_execution_profiles_missing")
    if not any(row["path"] == "modules/autonomy/services/robot_capability_map.py" and row["exists"] for row in files):
        blockers.append("runtime_capability_adapter_missing")
    if not cv2.get("importable"):
        warnings.append("cv2_not_importable")
    if not platform_info.get("is_robot_like"):
        warnings.append("not_running_on_linux_arm_robot_target")
    if devices.get("available") and not devices.get("video"):
        warnings.append("no_linux_video_device_found")
    if devices.get("available") and not devices.get("serial"):
        warnings.append("no_linux_serial_device_found")
    if not gateway_reachable:
        warnings.append("gateway_not_reachable")
    if start_error:
        warnings.append("gateway_start_command_failed")
    if str(cv2.get("version") or "").startswith("5."):
        warnings.append("opencv5_installed_research_required_before_pipeline_changes")

    forbidden = {endpoint: False for endpoint in FORBIDDEN_ENDPOINTS}

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_type": "robot_runtime_gateway_status_probe",
        "robot_first": True,
        "status_only": True,
        "no_camera_start": True,
        "no_snapshot": True,
        "no_video_stream": True,
        "no_vlm_inference": True,
        "no_hardware_enable": True,
        "gateway_base_url": args.gateway_base_url,
        "gateway_reachable": gateway_reachable,
        "started_command": started_command,
        "start_error": start_error,
        "platform": platform_info,
        "devices": devices,
        "cv2": cv2,
        "configs": configs,
        "files": files,
        "http_results": http_results,
        "forbidden_endpoints_called": forbidden,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next": [
            "Run this same Python tool on the robot target, not only on the PC.",
            "Keep SENTRYBOT_DISABLE_AUTOSTART=true for status probe unless explicitly doing activation.",
            "When status endpoints are reachable on robot, create a reversible camera start/stop plan.",
            "Research OpenCV 5 before changing detection/tracking/VLM pipeline.",
            "Do not enable motion/hardware until arm policy, capability registry, and robot safety CI pass on target.",
        ],
    }

    md = []
    md += [
        "# SentryBOT Robot Runtime Gateway Status Report",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "Robot-first, status-only probe. No camera start, no snapshot, no video stream, no VLM inference, no hardware enable.",
        "",
        "## Summary",
        "",
        table(["metric", "value"], [
            ["gateway_base_url", args.gateway_base_url],
            ["gateway_reachable", gateway_reachable],
            ["blockers", ", ".join(blockers) if blockers else "none"],
            ["warnings", ", ".join(warnings) if warnings else "none"],
            ["platform", f"{platform_info.get('system')} {platform_info.get('machine')}"],
            ["is_robot_like", platform_info.get("is_robot_like")],
            ["cv2_importable", cv2.get("importable")],
            ["cv2_version", cv2.get("version")],
            ["forbidden_endpoints_called", any(forbidden.values())],
        ]),
        "",
        "## Platform",
        "",
        table(["field", "value"], [[k, v] for k, v in platform_info.items()]),
        "",
        "## Robot Device Inventory",
        "",
        table(["field", "value"], [[k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v] for k, v in devices.items()]),
        "",
        "## Safe GET Results",
        "",
        table(["endpoint", "ok", "status", "elapsed_ms", "error/preview"], [
            [
                r.get("endpoint"),
                r.get("ok"),
                r.get("status", r.get("http_status", "")),
                r.get("elapsed_ms"),
                r.get("error", "") or json.dumps(r.get("json", r.get("text_preview", "")), ensure_ascii=False),
            ]
            for r in http_results
        ]),
        "",
        "## OpenCV / cv2",
        "",
        table(["field", "value"], [[k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v] for k, v in cv2.items()]),
        "",
        "## Runtime Files",
        "",
        table(["path", "exists", "lines", "robot_terms"], [
            [r["path"], r["exists"], r.get("lines", ""), ", ".join(r.get("robot_terms", []))]
            for r in files
        ]),
        "",
        "## Config Files",
        "",
        table(["path", "exists", "lines", "summary"], [
            [r["path"], r["exists"], r.get("lines", ""), json.dumps(r.get("summary", {}), ensure_ascii=False)]
            for r in configs
        ]),
        "",
        "## Recommended Next",
        "",
    ]
    for step in data["recommended_next"]:
        md.append(f"- {step}")
    md.append("")

    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print("[WRITE] ROBOT_RUNTIME_GATEWAY_STATUS_REPORT.md")
    print("[WRITE] robot_runtime_gateway_status_report.json")
    print(f"[SUMMARY] gateway_reachable={gateway_reachable}")
    print(f"[SUMMARY] blockers={len(blockers)}")
    print(f"[SUMMARY] warnings={len(warnings)}")
    print(f"[SUMMARY] is_robot_like={platform_info.get('is_robot_like')}")
    print(f"[SUMMARY] cv2_importable={cv2.get('importable')}")
    print(f"[SUMMARY] cv2_version={cv2.get('version')}")
    print("[SUMMARY] forbidden_endpoints_called=False")
    print("[DONE] robot runtime gateway status probe complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())