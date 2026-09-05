from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
from typing import Any

try:
    import psutil
except Exception:
    psutil = None


def _cpu_name_from_windows_registry() -> str | None:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return name.strip() if name else None
    except Exception:
        return None


def _cpu_name_from_device_tree() -> str | None:
    try:
        dt_path = Path("/proc/device-tree/model")
        if dt_path.exists():
            model_str = dt_path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
            return model_str or None
    except Exception:
        pass
    return None


def _cpu_name_from_proc_cpuinfo() -> str | None:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(("Model", "model name", "Hardware")):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _cores_fallback() -> str:
    c = os.cpu_count()
    return str(c) if c else "?"


def _freq_from_sysfs() -> str | None:
    try:
        freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
        if not freq_path.exists():
            freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        if freq_path.exists():
            khz = int(freq_path.read_text().strip())
            return f"{khz // 1000} MHz"
    except Exception:
        pass
    return None


def _psutil_cpu_stats() -> tuple[str, str, str]:
    """Returns (cores, freq, usage); '?' placeholders on any failure."""
    cores, freq, usage = "?", "?", "?"
    if psutil:
        try:
            cores = str(psutil.cpu_count(logical=True) or "?")
            freq_info = psutil.cpu_freq()
            if freq_info:
                freq = f"{freq_info.current:.0f} MHz"
            usage = f"{psutil.cpu_percent(interval=0.1):.1f}%"
        except Exception:
            pass
    return cores, freq, usage


def get_cpu_info() -> tuple[str, str, str, str]:
    cpu_name = platform.processor() or "Unknown"
    cores, freq, usage = _psutil_cpu_stats()

    if os.name == "nt":
        name = _cpu_name_from_windows_registry()
        if name:
            cpu_name = name
        if cores == "?":
            cores = _cores_fallback()
    else:
        if cpu_name in ("", "Unknown"):
            cpu_name = (
                _cpu_name_from_device_tree()
                or _cpu_name_from_proc_cpuinfo()
                or cpu_name
            )
        if cores == "?":
            cores = _cores_fallback()
        if freq == "?":
            freq = _freq_from_sysfs() or "?"

    return cpu_name.strip() or "Unknown", cores, freq, usage


def get_memory_info() -> tuple[str, str]:
    if psutil:
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            return f"{used_gb:.1f} GiB", f"{total_gb:.1f} GiB"
        except Exception:
            pass
    if os.name == "nt":
        try:
            import ctypes
            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            s = _MEMSTAT()
            s.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
                used = s.ullTotalPhys - s.ullAvailPhys
                return f"{used / (1024**3):.1f} GiB", f"{s.ullTotalPhys / (1024**3):.1f} GiB"
        except Exception:
            pass
    else:
        try:
            meminfo: dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        val = parts[1].strip().split()[0]
                        if val.isdigit():
                            meminfo[parts[0].strip()] = int(val) * 1024
            if "MemTotal" in meminfo:
                total = meminfo["MemTotal"]
                avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
                used = max(0, total - avail)
                return f"{used / (1024**3):.1f} GiB", f"{total / (1024**3):.1f} GiB"
        except Exception:
            pass
    return "N/A", "N/A"


def get_disk_info() -> tuple[str, str]:
    if psutil:
        try:
            root = "C:\\" if os.name == "nt" else "/"
            disk = psutil.disk_usage(root)
            used_gb = disk.used / (1024**3)
            total_gb = disk.total / (1024**3)
            return f"{used_gb:.1f} GiB", f"{total_gb:.1f} GiB"
        except Exception:
            pass
    try:
        root = "C:\\" if os.name == "nt" else "/"
        total_b, used_b, _ = shutil.disk_usage(root)
        used_gb = used_b / (1024**3)
        total_gb = total_b / (1024**3)
        return f"{used_gb:.1f} GiB", f"{total_gb:.1f} GiB"
    except Exception:
        pass
    return "N/A", "N/A"


def get_gpu_info() -> str:
    if os.name == "nt":
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | Format-Table -AutoSize"],
                capture_output=True, text=True, timeout=5
            )
            gpus = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("Name") and not line.startswith("----"):
                    parts = line.rsplit(" ", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        ram_gb = int(parts[1]) / (1024**3)
                        gpus.append(f"{parts[0]} ({ram_gb:.1f} GiB)")
                    else:
                        gpus.append(parts[0])
            if gpus:
                return ", ".join(gpus[:2])
        except Exception:
            pass
    else:
        try:
            dt_path = Path("/proc/device-tree/model")
            if dt_path.exists():
                dt_text = dt_path.read_text(encoding="utf-8", errors="ignore").lower()
                if "raspberry pi 5" in dt_text:
                    return "Broadcom VideoCore VII"
                if "raspberry pi 4" in dt_text:
                    return "Broadcom VideoCore VI"
                if "raspberry pi" in dt_text:
                    return "Broadcom VideoCore IV"
        except Exception:
            pass
        try:
            import subprocess
            result = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    return line.split(":", 2)[-1].strip()[:80]
        except Exception:
            pass
    return "Unknown"


def get_resolution() -> str:
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            return f"{w}x{h}"
        except Exception:
            pass
    return "Unknown"


def get_battery() -> str:
    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            batt = psutil.sensors_battery()
            if batt:
                plugged = " (Plugged In)" if batt.power_plugged else ""
                return f"{batt.percent:.0f}%{plugged}"
        except Exception:
            pass
    return "Unknown"
