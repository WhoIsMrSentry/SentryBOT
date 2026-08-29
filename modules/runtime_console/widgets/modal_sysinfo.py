from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from ..services.system_info_collector import get_system_info
from ..services.tui_ascii_helpers import load_ascii_art


class SysInfoModal(ModalScreen[None]):
    """System Telemetry and hardware specifications modal dialog."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("i", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="sysinfo_dialog"):
            yield Label("[SYSTEM HARDWARE & TELEMETRY SPECS]", id="sysinfo_title")
            with VerticalScroll(id="sysinfo_scroll"):
                yield Static(id="sysinfo_content")
            yield Button("Close (Esc)", id="sysinfo_close_btn", variant="primary")

    def on_mount(self) -> None:
        self.load_info()

    def load_info(self) -> None:
        try:
            info = get_system_info()
            ascii_art = load_ascii_art()
            
            rich_text = Text()
            for line in ascii_art[:10]:
                rich_text.append(line + "\n", style="bold #FA1E4E")
                
            rich_text.append("\n" + "─" * 55 + "\n", style="#500213")
            
            fields = [
                ("OS", info.os_name),
                ("Kernel", info.kernel),
                ("Host", info.hostname),
                ("Uptime", info.uptime),
                ("CPU", f"{info.cpu} ({info.cpu_cores} cores @ {info.cpu_freq}) [{info.cpu_usage}]"),
                ("Memory", f"{info.memory} / {info.memory_total}"),
                ("Disk", f"{info.disk} / {info.disk_total}"),
                ("GPU", info.gpu),
                ("Local IP", info.local_ip),
                ("Shell", info.shell),
                ("Python", info.python_version),
                ("SentryBOT", info.sentrybot_version),
            ]
            
            for label, val in fields:
                rich_text.append(f"{label:<14}: ", style="bold #FA1E4E")
                rich_text.append(f"{val}\n", style="white")
                
            self.query_one("#sysinfo_content", Static).update(rich_text)
        except Exception as exc:
            self.query_one("#sysinfo_content", Static).update(f"Error loading sysinfo: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sysinfo_close_btn":
            self.dismiss()
