
from __future__ import annotations
import glob
import importlib.util
import os
import platform
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional
from modules.common.model_asset_truth import collect_asset_truth

def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""

def is_raspberry_pi() -> bool:
    model = _read("/proc/device-tree/model") or _read("/sys/firmware/devicetree/base/model")
    return "raspberry pi" in model.lower()

class PiHardwareRuntime:
    DEFAULTS = {"require_pi": True, "require_camera": True, "require_esp": False, "camera_device_glob": "/dev/video*"}
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self.client = client
        self._last: Dict[str, Any] = {"ok": False, "reason": "never_checked"}
    def status(self) -> Dict[str, Any]:
        model = _read("/proc/device-tree/model") or _read("/sys/firmware/devicetree/base/model")
        pi = is_raspberry_pi()
        video_devices = sorted(glob.glob(str(self.cfg.get("camera_device_glob") or "/dev/video*")))
        picamera2 = importlib.util.find_spec("picamera2") is not None
        libcamera = bool(Path("/usr/bin/libcamera-hello").exists()) or bool(os.environ.get("LIBCAMERA_LOG_LEVEL"))
        assets = collect_asset_truth(Path.cwd())
        esp = self._esp_status()
        ok = True
        reasons = []
        if self.cfg.get("require_pi", True) and not pi:
            ok = False; reasons.append("not_raspberry_pi")
        if self.cfg.get("require_camera", True) and not (picamera2 and (video_devices or pi)):
            ok = False; reasons.append("camera_stack_missing")
        if self.cfg.get("require_esp", False) and not esp.get("ok"):
            ok = False; reasons.append("esp_unreachable")
        if assets.get("required_missing"):
            ok = False; reasons.append("required_assets_missing")
        out = {"ok": ok, "available": True, "timestamp": time.time(), "hostname": socket.gethostname(), "machine": platform.machine(), "platform": platform.platform(), "model": model, "is_raspberry_pi": pi, "picamera2_available": picamera2, "libcamera_present": libcamera, "video_devices": video_devices, "esp": esp, "assets": assets, "reason": "ok" if ok else ",".join(reasons)}
        self._last = out
        return out
    def _esp_status(self) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "reason": "client_missing"}
        try:
            resp = self.client.robot_command("hello")
            return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "response": resp}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
    def last(self) -> Dict[str, Any]:
        return dict(self._last)

__all__ = ["PiHardwareRuntime", "is_raspberry_pi"]
