from __future__ import annotations
import argparse, importlib.util, json, platform, shutil, subprocess
from pathlib import Path

def root() -> Path:
    return Path(__file__).resolve().parents[1]

def exists_nonempty_dir(p: Path) -> bool:
    return p.is_dir() and any(p.iterdir())

def check_file(path: str) -> dict:
    p = Path(path)
    return {"path": str(p), "ok": p.is_file()}

def check_dir(path: str) -> dict:
    p = Path(path)
    return {"path": str(p), "ok": exists_nonempty_dir(p)}

def check_module(name: str) -> dict:
    return {"name": name, "ok": importlib.util.find_spec(name) is not None}

def check_command(name: str) -> dict:
    found = shutil.which(name)
    return {"name": name, "ok": bool(found), "path": found or ""}

def collect() -> dict:
    r = root()
    model = ""
    try:
        model = Path("/proc/device-tree/model").read_text(errors="ignore").replace("\x00", "").strip()
    except Exception:
        pass
    checks = {
        "system": {"os": platform.system().lower(), "machine": platform.machine(), "model": model, "is_linux": platform.system().lower() == "linux", "is_raspberry_pi": "Raspberry Pi" in model},
        "files": {
            "piper_tr_model": check_file(str(r / "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx")),
            "piper_tr_config": check_file(str(r / "data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx.json")),
            "imx500_model": check_file("/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"),
        },
        "python_modules": {m: check_module(m) for m in ["picamera2", "numpy", "cv2", "speech_recognition", "openwakeword", "piper", "fastapi", "uvicorn"]},
        "commands": {c: check_command(c) for c in ["rpicam-hello", "rpicam-vid", "aplay", "arecord", "ollama"]},
    }
    required = []
    if not checks["system"]["is_linux"]: required.append("linux")
    if not checks["system"]["is_raspberry_pi"]: required.append("raspberry_pi")
    for k in ["piper_tr_model", "piper_tr_config", "imx500_model"]:
        if not checks["files"][k]["ok"]: required.append(k)
    for k in ["picamera2", "numpy", "cv2", "speech_recognition", "openwakeword", "fastapi", "uvicorn"]:
        if not checks["python_modules"][k]["ok"]: required.append("python_module:" + k)
    for k in ["rpicam-hello", "aplay", "arecord"]:
        if not checks["commands"][k]["ok"]: required.append("command:" + k)
    checks["required_missing"] = required
    checks["ok"] = not required
    return checks

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail-on-required", action="store_true")
    args = ap.parse_args()
    data = collect()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.fail_on_required and not data["ok"]:
        return 2
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
