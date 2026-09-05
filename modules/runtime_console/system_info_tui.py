#!/usr/bin/env python3
"""
SentryBOT System Info TUI - Neofetch/fastfetch style system information display
Displays ASCII art logo and system information in a TUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
import time

repo_root = str(Path(__file__).resolve().parents[2])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from modules.runtime_console.services.system_info_collector import (
    SystemInfo,
    get_system_info,
    get_os_name,
    get_kernel,
    get_hostname,
    get_uptime,
    get_cpu_info,
    get_memory_info,
    get_disk_info,
    get_gpu_info,
    get_resolution,
    get_battery,
    get_local_ip,
    get_shell,
    get_terminal,
    get_terminal_font,
    get_package_count,
    get_python_version,
    get_sentrybot_version,
)
from modules.runtime_console.services.tui_ascii_helpers import (
    ASCII_ART_PATH,
    Palette,
    get_terminal_size,
    enable_virtual_terminal,
    scale_ascii_art,
    load_ascii_art,
    get_ascii_art_width,
    crop_ansi,
)
from modules.runtime_console.themes import get_saved_theme_name, get_theme


@dataclass
class UIState:
    width: int = 80
    height: int = 24
    ascii_art: list[str] = field(default_factory=list)
    info_lines: list[str] = field(default_factory=list)
    scroll_offset: int = 0
    color_enabled: bool = True
    running: bool = True


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
    if info.graphics and info.graphics != "Unknown":
        lines.append(fmt("Graphics:", info.graphics))
    
    if info.resolution and info.resolution != "Unknown":
        lines.append(fmt("Resolution:", info.resolution))
    
    if info.battery and info.battery != "Unknown":
        lines.append(fmt("Battery:", info.battery))
        
    if info.local_ip and info.local_ip != "Unknown":
        lines.append(fmt("Local IP:", info.local_ip))
        
    lines.append(fmt("Shell:", info.shell))
    if info.terminal_font and info.terminal_font != "unknown":
        lines.append(fmt("Font:", info.terminal_font))
    lines.append(fmt("Packages:", info.packages))
    lines.append(fmt("Python:", info.python_version))
    lines.append(fmt("Gateway:", f"http://{info.local_ip if info.local_ip != 'Unknown' else '127.0.0.1'}:8080"))
    lines.append(fmt("SentryBOT:", info.sentrybot_version))

    if pal.enabled:
        lines.append("")
        row1 = "".join(f"\x1b[{c}m   \x1b[0m" for c in range(40, 48))
        row2 = "".join(f"\x1b[{c}m   \x1b[0m" for c in range(100, 108))
        lines.append(row1)
        lines.append(row2)

    return lines


def render_frame(state: UIState, pal: Palette, primary_color: str) -> list[str]:
    width, height = state.width, state.height
    art = state.ascii_art
    info_lines = state.info_lines

    art_width = get_ascii_art_width(art)
    gap = "  "
    right_start = art_width + len(gap)
    available_right = max(10, width - right_start)

    output = []
    for i in range(height - 1):
        line_parts = []
        if i < len(art):
            art_line = art[i]
            line_parts.append(pal.hex(art_line.ljust(art_width), primary_color))
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


def run_tui() -> int:
    enable_virtual_terminal()

    state = UIState()
    state.width, state.height = get_terminal_size()
    pal = Palette(enabled=True)

    state.ascii_art = load_ascii_art()
    info = get_system_info()
    state.info_lines = format_info_lines(info, pal)

    saved_theme_name = get_saved_theme_name()
    theme_obj = get_theme(saved_theme_name)
    primary_color = theme_obj.primary

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
            frame = render_frame(state, pal, primary_color)
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

        saved_theme_name = get_saved_theme_name()
        theme_obj = get_theme(saved_theme_name)
        primary_color = theme_obj.primary

        width, height = get_terminal_size()
        art_width = get_ascii_art_width(art)
        available_right = max(10, width - art_width - 3)

        max_rows = max(len(art), len(lines))
        for i in range(max_rows):
            left = art[i] if i < len(art) else ""
            right = crop_ansi(lines[i], available_right) if i < len(lines) else ""
            print(f"{pal.hex(left.ljust(art_width), primary_color)}  {right}")
        return 0

    return run_tui()


if __name__ == "__main__":
    sys.exit(main())