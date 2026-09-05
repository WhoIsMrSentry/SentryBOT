from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

try:
    import psutil
except Exception:
    psutil = None

from .system_info_hardware import (
    get_cpu_info,
    get_memory_info,
    get_disk_info,
    get_gpu_info,
    get_resolution,
    get_battery,
)


@dataclass
class SystemInfo:
    os_name: str = ""
    kernel: str = ""
    hostname: str = ""
    uptime: str = ""
    cpu: str = ""
    cpu_cores: str = ""
    cpu_freq: str = ""
    cpu_usage: str = ""
    memory: str = ""
    memory_total: str = ""
    disk: str = ""
    disk_total: str = ""
    gpu: str = ""
    resolution: str = ""
    battery: str = ""
    local_ip: str = ""
    shell: str = ""
    terminal: str = ""
    terminal_font: str = ""
    packages: str = ""
    python_version: str = ""
    sentrybot_version: str = ""


def get_os_name() -> str:
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            name, _ = winreg.QueryValueEx(key, "ProductName")
            build, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
            winreg.CloseKey(key)
            if name.startswith("Windows"):
                return f"{name} ({build})"
            return f"Windows {name} ({build})"
        except Exception:
            return f"Windows {platform.version()}"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.system()


def get_kernel() -> str:
    return platform.release()


def get_hostname() -> str:
    return platform.node()


def get_uptime() -> str:
    if psutil:
        try:
            boot = psutil.boot_time()
            secs = int(time.time() - boot)
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if mins:
                parts.append(f"{mins}m")
            parts.append(f"{secs}s")
            return " ".join(parts)
        except Exception:
            pass
    if os.name == "nt":
        try:
            import ctypes
            tick = ctypes.windll.kernel32.GetTickCount64()
            secs = tick // 1000
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if mins:
                parts.append(f"{mins}m")
            parts.append(f"{secs}s")
            return " ".join(parts)
        except Exception:
            pass
    else:
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                secs = int(float(f.read().split()[0]))
                days, rem = divmod(secs, 86400)
                hours, rem = divmod(rem, 3600)
                mins, secs = divmod(rem, 60)
                parts = []
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                if mins:
                    parts.append(f"{mins}m")
                parts.append(f"{secs}s")
                return " ".join(parts)
        except Exception:
            pass
    return "unknown"


def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    return "Unknown"


def get_shell() -> str:
    shell = os.environ.get("SHELL", "")
    if shell:
        return Path(shell).name
    if os.name == "nt":
        return os.environ.get("ComSpec", "cmd.exe").split("\\")[-1]
    return "unknown"


def get_terminal() -> str:
    term = os.environ.get("TERM", "")
    term_prog = os.environ.get("TERM_PROGRAM", "")
    wt_session = os.environ.get("WT_SESSION", "")
    if wt_session:
        return "Windows Terminal"
    if term_prog:
        return term_prog
    if term:
        return term
    if os.name == "nt":
        return "cmd.exe"
    return "unknown"


def get_terminal_font() -> str:
    return "unknown"


def get_package_count() -> str:
    if os.name == "nt":
        try:
            import subprocess
            result = subprocess.run(
                ["winget", "list", "--count"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if "Packages" in line or "package" in line.lower():
                    return line.strip()
        except Exception:
            pass
        try:
            import subprocess
            result = subprocess.run(
                ["choco", "list", "--local-only", "--limit-output"],
                capture_output=True, text=True, timeout=10
            )
            count = len([l for l in result.stdout.splitlines() if l.strip()])
            return f"{count} (choco)"
        except Exception:
            pass
        return "unknown"
    else:
        for cmd in [["dpkg", "-l"], ["pacman", "-Q"], ["rpm", "-qa"], ["apk", "info"]]:
            try:
                import subprocess
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if cmd[0] == "dpkg":
                    count = len([l for l in result.stdout.splitlines() if l.startswith("ii")])
                else:
                    count = len([l for l in result.stdout.splitlines() if l.strip()])
                if count > 0:
                    return f"{count} ({cmd[0]})"
            except Exception:
                continue
    return "unknown"


def get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_sentrybot_version() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        version_file = root / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            import re
            content = pyproject.read_text()
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return "dev"


def get_system_info() -> SystemInfo:
    info = SystemInfo()
    info.os_name = get_os_name()
    info.kernel = get_kernel()
    info.hostname = get_hostname()
    info.uptime = get_uptime()
    info.cpu, info.cpu_cores, info.cpu_freq, info.cpu_usage = get_cpu_info()
    info.memory, info.memory_total = get_memory_info()
    info.disk, info.disk_total = get_disk_info()
    info.gpu = get_gpu_info()
    info.resolution = get_resolution()
    info.battery = get_battery()
    info.local_ip = get_local_ip()
    info.shell = get_shell()
    info.terminal = get_terminal()
    info.terminal_font = get_terminal_font()
    info.packages = get_package_count()
    info.python_version = get_python_version()
    info.sentrybot_version = get_sentrybot_version()
    return info
