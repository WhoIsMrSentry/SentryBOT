from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

from .models import Snapshot, TABS, UIState, edit_yaml, project_search
from .robot_process import (
    execute_companion_goal_dry_run,
    refresh_camera_snapshot,
    refresh_companion_snapshot,
    refresh_expression_output_snapshot,
    refresh_expression_snapshot,
    tick_companion_auto_dry_run,
)


def enable_virtual_terminal() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class KeyReader:
    def __init__(self) -> None:
        self.windows = os.name == "nt"
        self.old_term: Any = None
        if not self.windows:
            import termios
            import tty

            self.termios = termios
            self.tty = tty

    def __enter__(self) -> "KeyReader":
        if not self.windows and sys.stdin.isatty():
            self.old_term = self.termios.tcgetattr(sys.stdin)
            self.tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_: Any) -> None:
        if not self.windows and self.old_term is not None:
            self.termios.tcsetattr(sys.stdin, self.termios.TCSADRAIN, self.old_term)

    def read(self) -> str | None:
        if self.windows:
            import msvcrt

            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                nxt = msvcrt.getwch()
                return {
                    "H": "UP",
                    "P": "DOWN",
                    "K": "LEFT",
                    "M": "RIGHT",
                    "G": "HOME",
                    "O": "END",
                    "I": "PGUP",
                    "Q": "PGDN",
                }.get(nxt)
            if ch == "\r":
                return "ENTER"
            if ch == "\x08":
                return "BACKSPACE"
            if ch == "\x1b":
                return "ESC"
            return ch
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {
                "[A": "UP",
                "[B": "DOWN",
                "[D": "LEFT",
                "[C": "RIGHT",
                "[5": "PGUP",
                "[6": "PGDN",
            }.get(seq, "ESC")
        if ch in ("\n", "\r"):
            return "ENTER"
        if ch in ("\x7f", "\b"):
            return "BACKSPACE"
        return ch


def handle_command(ui: UIState, snapshot: Snapshot, text: str) -> None:
    text = text.strip()
    if not text:
        return
    parts = text.split()
    cmd = parts[0].lower()
    arg = text[len(parts[0]) :].strip() if parts else ""
    if cmd in {"q", "quit", "exit"}:
        ui.message = "quit requested"
        raise KeyboardInterrupt
    if cmd == "profile" and arg.lower() in {"pc", "pc-test", "test"}:
        ui.profile = "pc-test"
        ui.message = "profile set to PC TEST"
    elif cmd == "profile" and arg.lower() in {"robot", "rpi", "pi"}:
        ui.profile = "robot"
        ui.message = "profile set to ROBOT"
    elif cmd in {"filter", "f"}:
        ui.filter_text = arg
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"filter set: {arg}"
    elif cmd == "view" and arg.lower() in {"human", "full", "warn"}:
        ui.log_view = arg.lower()
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"log view set: {ui.log_view}"
    elif cmd in {"search", "s"}:
        ui.project_search = arg
        ui.project_results = project_search(ui.root, arg)
        ui.active_tab = 4
        ui.message = f"search complete: {len(ui.project_results)} results"
    elif cmd == "camera" and arg.lower() in {"refresh", "status", "probe"}:
        refresh_camera_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Camera") if "Camera" in TABS else ui.active_tab
        ui.message = "camera status refreshed"
    elif cmd in {"memorybias", "bias", "shadow"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "memory shadow/bias refreshed"
    elif cmd in {"memory", "mem", "worldmemory"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "world memory refreshed"
    elif cmd in {"looptick", "loop", "behaviorloop"}:
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion behavior loop dry-run tick executed"
    elif cmd in {"autotick", "autoexecute", "autogoal"}:
        tick_companion_auto_dry_run(snapshot)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion auto gate dry-run tick executed"
    elif cmd in {"execute", "dryrun", "goalrun"}:
        execute_companion_goal_dry_run(snapshot)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion goal dry-run executed"
    elif cmd in {"companion", "goal", "needs"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion goal refreshed"
    elif cmd == "expression" and (arg.lower() in {"refresh", "status", "state", "probe"} or not arg):
        refresh_expression_snapshot(snapshot, force=True)
        refresh_expression_output_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Expression") if "Expression" in TABS else ui.active_tab
        ui.message = "expression state refreshed"
    elif cmd == "tab" and arg:
        for idx, name in enumerate(TABS):
            if name.lower().startswith(arg.lower()):
                ui.active_tab = idx
                return
        ui.message = f"unknown tab: {arg}"
    elif cmd == "set" and len(parts) >= 3:
        key = parts[1]
        value = text.split(None, 2)[2]
        ui.message = edit_yaml(ui.root, ui.selected_config, key, value)
    else:
        ui.message = f"unknown command: {cmd}"


def _submit_command_buffer(mode: str, buf: str, ui: UIState, snapshot: Snapshot) -> None:
    if mode == "filter":
        ui.filter_text = buf.strip()
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"filter set: {ui.filter_text or '<none>'}"
    elif mode == "project_search":
        ui.project_search = buf.strip()
        ui.project_results = project_search(ui.root, ui.project_search)
        ui.active_tab = 4
        ui.message = f"search complete: {len(ui.project_results)} results"
    elif mode == "command":
        handle_command(ui, snapshot, buf)
    elif mode == "edit_key":
        ui.pending_key = buf.strip()
        ui.command_mode = "edit_value"
    elif mode == "edit_value":
        ui.message = edit_yaml(ui.root, ui.selected_config, ui.pending_key, buf)
        ui.pending_key = ""


def _handle_command_mode_key(key: str, ui: UIState, snapshot: Snapshot) -> None:
    if key == "ESC":
        ui.command_mode = ""
        ui.command_buffer = ""
        ui.pending_key = ""
        return
    if key == "BACKSPACE":
        ui.command_buffer = ui.command_buffer[:-1]
        return
    if key == "ENTER":
        buf = ui.command_buffer
        mode = ui.command_mode
        ui.command_buffer = ""
        ui.command_mode = ""
        _submit_command_buffer(mode, buf, ui, snapshot)
        return
    if len(key) == 1 and key.isprintable():
        ui.command_buffer += key


def _handle_refresh_key(ui: UIState, snapshot: Snapshot) -> None:
    label = TABS[ui.active_tab] if 0 <= ui.active_tab < len(TABS) else ""
    if label == "Companion":
        refresh_companion_snapshot(snapshot, force=True)
        ui.message = "companion goal refreshed"
    elif label == "Camera":
        refresh_camera_snapshot(snapshot, force=True)
        ui.message = "camera status refreshed"
    elif label == "Expression":
        refresh_expression_snapshot(snapshot, force=True)
        refresh_expression_output_snapshot(snapshot, force=True)
        ui.message = "expression state/output refreshed"
    else:
        ui.message = "refreshed"


def _handle_shortcut_key(key: str, ui: UIState, snapshot: Snapshot) -> None:
    if key in {"v", "V"}:
        order = ["human", "full", "warn"]
        ui.log_view = (
            order[(order.index(ui.log_view) + 1) % len(order)]
            if ui.log_view in order
            else "human"
        )
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"log view: {ui.log_view}"
    elif key == "/":
        ui.command_mode = "filter"
        ui.command_buffer = ui.filter_text
    elif key in {"s", "S"}:
        ui.command_mode = "project_search"
        ui.command_buffer = ui.project_search
    elif key == ":":
        ui.command_mode = "command"
    elif key in {"e", "E"}:
        if ui.active_tab == 3:
            ui.command_mode = "edit_key"
            ui.command_buffer = ""
        else:
            ui.message = "edit is available on Config tab"
    elif key in {"c", "C"}:
        ui.filter_text = ""
        ui.project_search = ""
        ui.project_results = []
        ui.message = "cleared"
    elif key in {"r", "R"}:
        _handle_refresh_key(ui, snapshot)


def _handle_navigation_key(key: str, ui: UIState) -> None:
    if key == "UP":
        if ui.active_tab == 3:
            ui.selected_config = max(0, ui.selected_config - 1)
        elif ui.active_tab == 1:
            ui.selected_event = max(0, ui.selected_event - 1)
            ui.scroll = max(0, min(ui.scroll, ui.selected_event))
        else:
            ui.scroll += 1
    elif key == "DOWN":
        if ui.active_tab == 3:
            ui.selected_config += 1
        elif ui.active_tab == 1:
            ui.selected_event += 1
            ui.scroll = max(ui.scroll, ui.selected_event - 2)
        else:
            ui.scroll = max(0, ui.scroll - 1)
    elif key == "PGUP":
        if ui.active_tab == 1:
            ui.selected_event = max(0, ui.selected_event - 10)
            ui.scroll = max(0, min(ui.scroll, ui.selected_event))
        else:
            ui.scroll += 10
    elif key == "PGDN":
        if ui.active_tab == 1:
            ui.selected_event += 10
            ui.scroll = max(ui.scroll, ui.selected_event - 2)
        else:
            ui.scroll = max(0, ui.scroll - 10)


def handle_key(key: str | None, ui: UIState, snapshot: Snapshot) -> None:
    if key is None:
        return
    if ui.command_mode:
        _handle_command_mode_key(key, ui, snapshot)
        return

    if key in {"q", "Q"}:
        raise KeyboardInterrupt
    if key.isdigit() and 1 <= int(key) <= len(TABS):
        ui.active_tab = int(key) - 1
        ui.scroll = 0
        if ui.active_tab == 1:
            ui.selected_event = 0
        return
    _handle_shortcut_key(key, ui, snapshot)
    _handle_navigation_key(key, ui)
