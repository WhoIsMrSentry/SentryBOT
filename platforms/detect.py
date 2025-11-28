from __future__ import annotations
import sys
import os


def detect_platform() -> str:
    """Return a normalized platform key used for overrides.

    Values: "windows" | "rpi" | "linux" | "macos"
    """
    plat = sys.platform
    if plat.startswith("win"):
        return "windows"
    if plat == "darwin":
        return "macos"
    # Linux variants
    key = "linux"
    # Try to detect Raspberry Pi by device tree or model info
    try:
        if os.path.exists("/proc/device-tree/model"):
            with open("/proc/device-tree/model", "r", encoding="utf-8", errors="ignore") as f:
                model = f.read().lower()
            if "raspberry pi" in model:
                return "rpi"
    except Exception:
        pass
    return key
