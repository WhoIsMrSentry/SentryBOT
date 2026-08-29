from __future__ import annotations

from typing import List, Tuple
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog
from ..services.async_log_streamer import ParsedLogEntry


class TabLogs(Widget):
    """Full-width live log viewer with search, filtering, and rich syntax colors."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.active_level_filter = "ALL"
        self.search_query = ""
        self.auto_scroll_enabled = True
        self.log_history: List[Tuple[ParsedLogEntry, Text]] = []
        self.max_history = 2000
        self.count_total = 0
        self.count_info = 0
        self.count_warn = 0
        self.count_err = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="logs_container"):
            # Stats Strip
            with Horizontal(id="logs_stats_bar"):
                yield Label("LOG METRICS: Total: 0 | Info: 0 | Warn: 0 | Error: 0", id="log_stats_label")

            # Toolbar
            with Horizontal(id="logs_toolbar"):
                yield Input(placeholder="Filter / Search logs... (Press / to focus)", id="log_search_input")
                yield Button("ALL", id="btn_filter_all", classes="filter_btn", variant="primary")
                yield Button("INFO", id="btn_filter_info", classes="filter_btn", variant="default")
                yield Button("WARN", id="btn_filter_warn", classes="filter_btn", variant="default")
                yield Button("ERROR", id="btn_filter_err", classes="filter_btn", variant="default")
                yield Button("Auto-Scroll: ON", id="log_scroll_toggle", variant="primary")
                yield Button("Clear", id="log_clear_btn", variant="error")

            # Main Full-Width Rich Log
            yield RichLog(
                id="live_rich_log",
                highlight=True,
                markup=False,
                auto_scroll=True,
                wrap=False,
            )

    def add_log_entry(self, entry: ParsedLogEntry, rich_text: Text) -> None:
        if "urllib3.connectionpool" in entry.raw:
            return

        self.log_history.append((entry, rich_text))
        if len(self.log_history) > self.max_history:
            self.log_history.pop(0)

        self.count_total += 1
        if entry.level == "ERROR" or entry.level == "CRITICAL":
            self.count_err += 1
        elif entry.level == "WARN":
            self.count_warn += 1
        elif entry.level == "INFO":
            self.count_info += 1

        self._update_stats_label()

        if self._matches_filter(entry):
            try:
                rich_log = self.query_one("#live_rich_log", RichLog)
                rich_log.write(rich_text)
            except Exception:
                pass

    def _update_stats_label(self) -> None:
        try:
            lbl = self.query_one("#log_stats_label", Label)
            lbl.update(
                f"LOG METRICS: Total: {self.count_total} | Info: {self.count_info} | "
                f"Warn: {self.count_warn} | Error: {self.count_err} | Filter: {self.active_level_filter}"
            )
        except Exception:
            pass

    def _matches_filter(self, entry: ParsedLogEntry) -> bool:
        if self.active_level_filter != "ALL":
            if self.active_level_filter == "INFO" and entry.level not in ("INFO", "WARN", "ERROR", "CRITICAL"):
                return False
            if self.active_level_filter == "WARN" and entry.level not in ("WARN", "ERROR", "CRITICAL"):
                return False
            if self.active_level_filter == "ERROR" and entry.level not in ("ERROR", "CRITICAL"):
                return False

        if self.search_query:
            query = self.search_query.lower()
            if query not in entry.raw.lower():
                return False

        return True

    def refilter_logs(self) -> None:
        try:
            rich_log = self.query_one("#live_rich_log", RichLog)
            rich_log.clear()
            for entry, rich_text in self.log_history:
                if self._matches_filter(entry):
                    rich_log.write(rich_text)
        except Exception:
            pass

    def set_level_filter(self, level: str) -> None:
        self.active_level_filter = level
        for btn_id in ("btn_filter_all", "btn_filter_info", "btn_filter_warn", "btn_filter_err"):
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                btn.variant = "default"
            except Exception:
                pass

        active_id = "btn_filter_all"
        if level == "INFO":
            active_id = "btn_filter_info"
        elif level == "WARN":
            active_id = "btn_filter_warn"
        elif level == "ERROR":
            active_id = "btn_filter_err"

        try:
            self.query_one(f"#{active_id}", Button).variant = "primary"
        except Exception:
            pass

        self._update_stats_label()
        self.refilter_logs()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log_search_input":
            self.search_query = event.value.strip()
            self.refilter_logs()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn_filter_all":
            self.set_level_filter("ALL")
        elif btn_id == "btn_filter_info":
            self.set_level_filter("INFO")
        elif btn_id == "btn_filter_warn":
            self.set_level_filter("WARN")
        elif btn_id == "btn_filter_err":
            self.set_level_filter("ERROR")
        elif btn_id == "log_clear_btn":
            self.log_history.clear()
            self.count_total = 0
            self.count_info = 0
            self.count_warn = 0
            self.count_err = 0
            self._update_stats_label()
            self.refilter_logs()
        elif btn_id == "log_scroll_toggle":
            self.auto_scroll_enabled = not self.auto_scroll_enabled
            try:
                rich_log = self.query_one("#live_rich_log", RichLog)
                rich_log.auto_scroll = self.auto_scroll_enabled
                event.button.label = "Auto-Scroll: ON" if self.auto_scroll_enabled else "Auto-Scroll: OFF"
                event.button.variant = "primary" if self.auto_scroll_enabled else "default"
            except Exception:
                pass
