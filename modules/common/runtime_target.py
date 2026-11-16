from __future__ import annotations

import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class RuntimeTarget:
    system: str
    machine: str
    model: str
    is_raspberry_pi: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _read_model() -> str:
    path = Path("/proc/device-tree/model")
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
    except OSError:
        return ""


def detect_runtime_target() -> RuntimeTarget:
    system = platform.system().strip().lower()
    machine = platform.machine().strip().lower()
    model = _read_model()
    is_linux = system == "linux"
    is_arm64 = machine in {"aarch64", "arm64"}
    is_pi_model = "raspberry pi" in model.lower()
    ok = is_linux and is_arm64 and is_pi_model
    if ok:
        reason = "raspberry_pi_detected"
    elif not is_linux:
        reason = "linux_required"
    elif not is_arm64:
        reason = "arm64_required"
    else:
        reason = "raspberry_pi_model_not_detected"
    return RuntimeTarget(system, machine, model, ok, reason)


def assert_raspberry_pi(allow_pc_fallback: bool | None = None) -> RuntimeTarget:
    target = detect_runtime_target()
    if not target.is_raspberry_pi:
        if allow_pc_fallback is None:
            allow_pc_fallback = (
                os.environ.get("SENTRYBOT_ALLOW_PC_FALLBACK") == "1"
                or os.environ.get("SENTRYBOT_PC_TEST") == "1"
                or os.environ.get("SENTRYBOT_PROFILE") in {"pc", "pc-test"}
            )
        if allow_pc_fallback:
            return target
        raise RuntimeError(
            "SentryBOT robot runtime only supports Raspberry Pi 5. "
            f"system={target.system!r} machine={target.machine!r} "
            f"model={target.model!r} reason={target.reason}"
        )
    return target


def _read_cpu_temp_c(thermal_path: Path = Path("/sys/class/thermal/thermal_zone0/temp")) -> float | None:
    try:
        raw = thermal_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw:
            return None
        val = float(raw)
        return round(val / 1000.0 if val > 200.0 else val, 1)
    except (OSError, ValueError):
        return None


def _read_mem_available_mb(meminfo_path: Path = Path("/proc/meminfo")) -> float | None:
    try:
        for line in meminfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemAvailable:"):
                kb = float(line.split()[1])
                return round(kb / 1024.0, 1)
    except (OSError, ValueError, IndexError):
        return None
    return None


def read_hardware_pressure(
    *,
    thermal_path: Path = Path("/sys/class/thermal/thermal_zone0/temp"),
    meminfo_path: Path = Path("/proc/meminfo"),
    warn_temp_c: float = 72.0,
    critical_temp_c: float = 80.0,
    min_free_mem_mb: float = 512.0,
) -> Dict[str, Any]:
    """Return lightweight RPi5 thermal/memory pressure hints without subprocess overhead."""
    temp_c = _read_cpu_temp_c(thermal_path)
    mem_mb = _read_mem_available_mb(meminfo_path)
    pressure = "normal"
    if (temp_c is not None and temp_c >= critical_temp_c) or (mem_mb is not None and mem_mb < min_free_mem_mb / 2):
        pressure = "critical"
    elif (temp_c is not None and temp_c >= warn_temp_c) or (mem_mb is not None and mem_mb < min_free_mem_mb):
        pressure = "warm"
    return {
        "cpu_temp_c": temp_c,
        "mem_available_mb": mem_mb,
        "pressure_level": pressure,
        "eco_recommended": pressure != "normal",
    }


def status() -> Dict[str, Any]:
    target = detect_runtime_target()
    return {
        "ok": target.is_raspberry_pi,
        "target": "raspberry_pi_5" if target.is_raspberry_pi else "unsupported",
        "pressure": read_hardware_pressure(),
        **target.to_dict(),
    }


__all__ = [
    "RuntimeTarget",
    "detect_runtime_target",
    "assert_raspberry_pi",
    "read_hardware_pressure",
    "status",
]
