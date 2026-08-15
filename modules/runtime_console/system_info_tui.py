#!/usr/bin/env python3
"""
SentryBOT System Info TUI - Neofetch/fastfetch style system information display
Displays ASCII art logo and system information in a TUI.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:
    psutil = None


ASCII_ART_PATH = Path(__file__).parent.parent.parent / "data" / "ascii-art.txt"


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


@dataclass
class UIState:
    width: int = 80
    height: int = 24
    ascii_art: list[str] = field(default_factory=list)
    info_lines: list[str] = field(default_factory=list)
    scroll_offset: int = 0
    color_enabled: bool = True
    running: bool = True


class Palette:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def c(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def reset(self, text: str) -> str:
        return text

    def bold(self, text: str) -> str:
        return self.c(text, "1")

    def dim(self, text: str) -> str:
        return self.c(text, "2")

    def red(self, text: str) -> str:
        return self.c(text, "31")

    def green(self, text: str) -> str:
        return self.c(text, "32")

    def yellow(self, text: str) -> str:
        return self.c(text, "33")

    def blue(self, text: str) -> str:
        return self.c(text, "34")

    def magenta(self, text: str) -> str:
        return self.c(text, "35")

    def cyan(self, text: str) -> str:
        return self.c(text, "36")

    def white(self, text: str) -> str:
        return self.c(text, "37")

    def gray(self, text: str) -> str:
        return self.c(text, "90")


def get_terminal_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24


def enable_virtual_terminal() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def scale_ascii_art(art: list[str], target_w: int, target_h: int) -> list[str]:
    from collections import Counter
    orig_h = len(art)
    if orig_h == 0:
        return art
    orig_w = len(art[0])
    if orig_w == 0 or (orig_h <= target_h and orig_w <= target_w):
        return art

    scaled = []
    for ty in range(target_h):
        sy1 = int(ty * orig_h / target_h)
        sy2 = max(sy1 + 1, int((ty + 1) * orig_h / target_h))
        row = []
        for tx in range(target_w):
            sx1 = int(tx * orig_w / target_w)
            sx2 = max(sx1 + 1, int((tx + 1) * orig_w / target_w))
            
            chars = []
            for y in range(sy1, min(sy2, orig_h)):
                for x in range(sx1, min(sx2, orig_w)):
                    c = art[y][x]
                    if c != ' ':
                        chars.append(c)
            
            if not chars:
                row.append(' ')
            else:
                row.append(Counter(chars).most_common(1)[0][0])
        scaled.append(''.join(row))
    return scaled

def load_ascii_art() -> list[str]:
    import shutil
    try:
        if ASCII_ART_PATH.exists():
            content = ASCII_ART_PATH.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            # Strip top and bottom empty lines to align with OS info
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()

            if not lines:
                return ["SENTRYBOT"]

            min_indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
            lines = [l[min_indent:].rstrip() for l in lines]

            max_w = max((len(l) for l in lines), default=0)
            lines = [l.ljust(max_w) for l in lines]
            
            # Dynamically check terminal size. Only scale if it won't fit side-by-side with info (~40 cols)
            term_w = shutil.get_terminal_size((80, 24)).columns
            allowed_w = max(30, term_w - 45) # Leave 45 columns for info text
            
            if max_w > allowed_w:
                ratio = max_w / len(lines)
                target_w = allowed_w
                target_h = int(target_w / ratio)
                lines = scale_ascii_art(lines, target_w, target_h)
                
            return lines
    except Exception:
        pass
    fallback = [
        "  SENTRYBOT  ",
        "  ▄▄▄▄▄▄▄▄▄▄▄▄  ",
        "  ████████████  ",
        "  ▀▀▀▀▀▀▀▀▀▀▀▀  ",
    ]
    max_w = max(len(l) for l in fallback)
    return [l.ljust(max_w) for l in fallback]


def get_ascii_art_width(art: list[str]) -> int:
    return max((len(line) for line in art), default=0)


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


def get_cpu_info() -> tuple[str, str, str, str]:
    cpu_name = platform.processor() or "Unknown"
    cores = "?"
    freq = "?"
    usage = "?"

    if psutil:
        try:
            cores = str(psutil.cpu_count(logical=True) or "?")
            freq_info = psutil.cpu_freq()
            if freq_info:
                freq = f"{freq_info.current:.0f} MHz"
            usage = f"{psutil.cpu_percent(interval=0.1):.1f}%"
        except Exception:
            pass

    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if name:
                cpu_name = name.strip()
        except Exception:
            pass
        if cores == "?":
            c = os.cpu_count()
            if c:
                cores = str(c)
    else:
        if cpu_name in ("", "Unknown"):
            try:
                dt_path = Path("/proc/device-tree/model")
                if dt_path.exists():
                    model_str = dt_path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
                    if model_str:
                        cpu_name = model_str
            except Exception:
                pass
            if cpu_name in ("", "Unknown"):
                try:
                    with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith(("Model", "model name", "Hardware")):
                                cpu_name = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass
        if cores == "?":
            c = os.cpu_count()
            if c:
                cores = str(c)
        if freq == "?":
            try:
                freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
                if not freq_path.exists():
                    freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
                if freq_path.exists():
                    khz = int(freq_path.read_text().strip())
                    freq = f"{khz // 1000} MHz"
            except Exception:
                pass

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
        root = Path(__file__).parent.parent.parent
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


def format_info_lines(info: SystemInfo, pal: Palette, label_width: int = 18) -> list[str]:
    def fmt(label: str, value: str) -> str:
        label_colored = pal.bold(pal.cyan(label.ljust(label_width)))
        return f"{label_colored}{value}"

    lines = []
    lines.append(fmt("OS:", info.os_name))
    lines.append(fmt("Kernel:", info.kernel))
    lines.append(fmt("Host:", info.hostname))
    lines.append(fmt("Uptime:", info.uptime))
    
    cpu_str = f"{info.cpu} ({info.cpu_cores} cores @ {info.cpu_freq})"
    if info.cpu_usage and info.cpu_usage != "?":
        cpu_str += f" [{info.cpu_usage}]"
    lines.append(fmt("CPU:", cpu_str))
    
    lines.append(fmt("Memory:", f"{info.memory} / {info.memory_total}"))
    lines.append(fmt("Disk:", f"{info.disk} / {info.disk_total}"))
    lines.append(fmt("GPU:", info.gpu))
    
    if info.resolution and info.resolution != "Unknown":
        lines.append(fmt("Resolution:", info.resolution))
    
    if info.battery and info.battery != "Unknown":
        lines.append(fmt("Battery:", info.battery))
        
    if info.local_ip and info.local_ip != "Unknown":
        lines.append(fmt("Local IP:", info.local_ip))
        
    lines.append(fmt("Shell:", info.shell))
    lines.append(fmt("Terminal:", info.terminal))
    lines.append(fmt("Font:", info.terminal_font))
    lines.append(fmt("Packages:", info.packages))
    lines.append(fmt("Python:", info.python_version))
    lines.append(fmt("SentryBOT:", info.sentrybot_version))

    if pal.enabled:
        lines.append("")
        # Use spaces with background colors to avoid UnicodeEncodeError in Windows consoles
        row1 = "".join(f"\x1b[{c}m   \x1b[0m" for c in range(40, 48))
        row2 = "".join(f"\x1b[{c}m   \x1b[0m" for c in range(100, 108))
        lines.append(row1)
        lines.append(row2)

    return lines


def render_frame(state: UIState, pal: Palette) -> list[str]:
    width, height = state.width, state.height
    art = state.ascii_art
    info_lines = state.info_lines

    art_width = get_ascii_art_width(art)

    gap = "  "
    right_start = art_width + len(gap)
    available_right = max(10, width - right_start)

    output = []
    max_lines = max(len(art), len(info_lines))

    for i in range(height - 1):
        line_parts = []

        if i < len(art):
            art_line = art[i]
            line_parts.append(pal.green(art_line.ljust(art_width)))
        else:
            line_parts.append(" " * art_width)

        line_parts.append(gap)

        if i < len(info_lines):
            info_line = info_lines[i]
            line_parts.append(crop_ansi(info_line, available_right))
        else:
            line_parts.append("")

        output.append("".join(line_parts))

    status = pal.dim(f" ↑↓ scroll  q quit  |  {width}x{height}  ")
    output.append(status.ljust(width))

    return output


def crop_ansi(text: str, width: int) -> str:
    import re
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    plain = ansi_re.sub("", text)
    if len(plain) <= width:
        return text
    result = ""
    visible = 0
    i = 0
    while i < len(text) and visible < width:
        if text[i] == "\x1b" and i + 1 < len(text) and text[i+1] == "[":
            j = text.find("m", i)
            if j != -1:
                result += text[i:j+1]
                i = j + 1
                continue
        result += text[i]
        if text[i] != "\x1b":
            visible += 1
        i += 1
    return result + "\x1b[0m"


def run_tui() -> int:
    enable_virtual_terminal()

    state = UIState()
    state.width, state.height = get_terminal_size()
    pal = Palette(enabled=True)

    state.ascii_art = load_ascii_art()
    info = get_system_info()
    state.info_lines = format_info_lines(info, pal)

    try:
        import msvcrt
        is_windows = True
    except ImportError:
        import termios
        import tty
        is_windows = False

    if not is_windows:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    try:
        while state.running:
            state.width, state.height = get_terminal_size()

            frame = render_frame(state, pal)
            print("\x1b[H" + "\n".join(frame), end="", flush=True)

            if is_windows:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        key = msvcrt.getwch()
                        if key == "H":
                            state.scroll_offset = max(0, state.scroll_offset - 1)
                        elif key == "P":
                            state.scroll_offset = min(
                                max(0, len(state.info_lines) - state.height + 3),
                                state.scroll_offset + 1
                            )
                    elif key in ("q", "Q", "\x1b"):
                        state.running = False
                    elif key == "\r":
                        state.scroll_offset = 0
            else:
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    key = sys.stdin.read(1)
                    if key == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A":
                            state.scroll_offset = max(0, state.scroll_offset - 1)
                        elif seq == "[B":
                            state.scroll_offset = min(
                                max(0, len(state.info_lines) - state.height + 3),
                                state.scroll_offset + 1
                            )
                    elif key in ("q", "Q"):
                        state.running = False
                    elif key in ("\n", "\r"):
                        state.scroll_offset = 0

            time.sleep(0.05)

    finally:
        if not is_windows:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\x1b[0m\x1b[?25h", end="", flush=True)

    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SentryBOT System Info TUI (neofetch-style)")
    parser.add_argument("--no-color", action="store_true", help="Disable colors")
    parser.add_argument("--once", action="store_true", help="Print once and exit (no TUI)")
    parser.add_argument("--ascii-only", action="store_true", help="Use ASCII-only art")
    args = parser.parse_args(argv)

    if args.once:
        pal = Palette(enabled=not args.no_color)
        art = load_ascii_art()
        info = get_system_info()
        lines = format_info_lines(info, pal)

        width, height = get_terminal_size()
        art_width = get_ascii_art_width(art)
        available_right = max(10, width - art_width - 3)

        max_rows = max(len(art), len(lines))
        for i in range(max_rows):
            left = art[i] if i < len(art) else ""
            right = crop_ansi(lines[i], available_right) if i < len(lines) else ""
            print(f"{pal.green(left.ljust(art_width))}  {right}")
        return 0


    return run_tui()


if __name__ == "__main__":
    sys.exit(main())