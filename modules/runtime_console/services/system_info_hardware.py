from __future__ import annotations

import json
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


def _format_vram(bytes_val: int | float | None) -> str:
    if not bytes_val or bytes_val <= 0:
        return ""
    gib = bytes_val / (1024**3)
    rounded = round(gib)
    if abs(gib - rounded) < 0.15:
        return f"{rounded}.0 GiB"
    return f"{gib:.1f} GiB"


def _get_windows_gpu_devices() -> list[tuple[str, str]]:
    """Query accurate 64-bit QWORD VRAM from Windows Registry to bypass WMI 32-bit (4GB) cap."""
    devices: list[tuple[str, int | None]] = []
    try:
        import winreg
        reg_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as base_key:
            subkeys, _, _ = winreg.QueryInfoKey(base_key)
            for i in range(subkeys):
                sub_name = winreg.EnumKey(base_key, i)
                if not sub_name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(base_key, sub_name) as k:
                        name, _ = winreg.QueryValueEx(k, "DriverDesc")
                        name = str(name).strip()
                        if not name:
                            continue
                        vram: int | None = None
                        try:
                            qw, _ = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")
                            if isinstance(qw, int) and qw > 0:
                                vram = qw
                        except OSError:
                            pass
                        if vram is None:
                            try:
                                mem, _ = winreg.QueryValueEx(k, "HardwareInformation.MemorySize")
                                if isinstance(mem, int) and mem > 0:
                                    vram = mem
                            except OSError:
                                pass
                        devices.append((name, vram))
                except OSError:
                    pass
    except Exception:
        pass

    # Verify / refine with nvidia-smi if available for discrete NVIDIA cards
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                if "," in line:
                    n, m = line.split(",", 1)
                    mb = float(m.strip())
                    nv_bytes = int(mb * 1024 * 1024)
                    for idx, (dname, dvram) in enumerate(devices):
                        if "nvidia" in dname.lower():
                            devices[idx] = (dname, nv_bytes)
    except Exception:
        pass

    if devices:
        formatted_list: list[tuple[str, str]] = []
        for name, vram in devices:
            vram_str = _format_vram(vram)
            if vram_str:
                formatted_list.append((name, f"{name} ({vram_str})"))
            else:
                formatted_list.append((name, name))
        return formatted_list

    # Fallback to WMI/CIM if registry did not return entries
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5
        )
        raw = (result.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        entries: list[tuple[str, str]] = []
        for item in data:
            name = str(item.get("Name") or "").strip()
            if not name:
                continue
            ram = item.get("AdapterRAM")
            vram_str = _format_vram(ram) if (ram and isinstance(ram, int) and ram > 0) else ""
            entries.append((name, f"{name} ({vram_str})" if vram_str else name))
        return entries
    except Exception:
        return []


def get_gpu_and_graphics() -> tuple[str, str]:
    """Retrieve primary GPU and secondary/integrated graphics cleanly without merging or line-wrapping."""
    if os.name == "nt":
        entries = _get_windows_gpu_devices()
        if not entries:
            return "Unknown", ""

        if len(entries) == 1:
            return entries[0][1], ""

        # Classify into discrete GPU vs integrated graphics
        dgpu: str | None = None
        igpu: str | None = None

        for raw_name, formatted in entries:
            lower = raw_name.lower()
            is_dgpu_candidate = any(k in lower for k in ("nvidia", "geforce", "rtx", "gtx", "quadro", "radeon rx", "discrete"))
            is_igpu_candidate = any(k in lower for k in ("intel", "uhd", "iris", "integrated", "graphics", "apu"))

            if is_dgpu_candidate and dgpu is None:
                dgpu = formatted
            elif is_igpu_candidate and igpu is None:
                igpu = formatted

        # Fallback if classification was incomplete
        if dgpu is None and igpu is not None:
            remaining = [f for _, f in entries if f != igpu]
            dgpu = remaining[0] if remaining else igpu
            if dgpu == igpu:
                igpu = ""
        elif dgpu is not None and igpu is None:
            remaining = [f for _, f in entries if f != dgpu]
            igpu = remaining[0] if remaining else ""
        elif dgpu is None and igpu is None:
            dgpu = entries[0][1]
            igpu = entries[1][1] if len(entries) > 1 else ""

        return dgpu or "Unknown", igpu or ""
    else:
        try:
            dt_path = Path("/proc/device-tree/model")
            if dt_path.exists():
                dt_text = dt_path.read_text(encoding="utf-8", errors="ignore").lower()
                if "raspberry pi 5" in dt_text:
                    return "Broadcom VideoCore VII", ""
                if "raspberry pi 4" in dt_text:
                    return "Broadcom VideoCore VI", ""
                if "raspberry pi" in dt_text:
                    return "Broadcom VideoCore IV", ""
        except Exception:
            pass
        try:
            import subprocess
            result = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, timeout=5
            )
            vga_lines = []
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    vga_lines.append(line.split(":", 2)[-1].strip()[:80])
            if vga_lines:
                if len(vga_lines) == 1:
                    return vga_lines[0], ""
                return vga_lines[0], vga_lines[1]
        except Exception:
            pass
    return "Unknown", ""


def get_gpu_info() -> str:
    gpu, _ = get_gpu_and_graphics()
    return gpu


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
