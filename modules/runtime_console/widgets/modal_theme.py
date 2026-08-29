from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option
from textual import on
from ..themes import THEMES, get_theme_names


class ThemeSelectorModal(ModalScreen[None]):
    """Live theme selector modal with real-time dynamic rendering."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("t", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="theme_dialog"):
            yield Label("[THEME SELECTION - LIVE PREVIEW]", id="theme_dialog_title")
            yield Label("Scroll or select to preview theme live in the background.", id="theme_hint")
            yield OptionList(id="theme_option_list")
            with Horizontal(id="theme_footer_bar"):
                yield Button("Close (Esc)", id="theme_btn_close", variant="primary", classes="theme_footer_btn")

    def on_mount(self) -> None:
        opt_list = self.query_one("#theme_option_list", OptionList)
        opt_list.clear_options()
        
        current_theme = getattr(self.app, "theme", "sentry-crimson")
        highlight_idx = 0
        
        for idx, (name, theme_obj) in enumerate(THEMES.items()):
            label = f"{name.upper():<18} | Primary: {theme_obj.primary} | Secondary: {theme_obj.secondary or '-'}"
            opt_list.add_option(Option(prompt=label, id=name))
            if name == current_theme:
                highlight_idx = idx

        opt_list.highlighted = highlight_idx

    @on(OptionList.OptionHighlighted, "#theme_option_list")
    def handle_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Live theme rendering as user navigates options."""
        if event.option_id:
            theme_name = str(event.option_id)
            if theme_name in THEMES:
                self.app.theme = theme_name
                from ..themes import save_theme_name
                save_theme_name(theme_name)
                self.notify(f"Live preview: {theme_name.upper()}", severity="information", timeout=1.0)

    @on(OptionList.OptionSelected, "#theme_option_list")
    def handle_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Apply theme on enter/click without closing the dialog."""
        if event.option_id:
            theme_name = str(event.option_id)
            if theme_name in THEMES:
                self.app.theme = theme_name
                from ..themes import save_theme_name
                save_theme_name(theme_name)
                self.notify(f"Theme applied: {theme_name.upper()}", severity="information", timeout=2.0)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "theme_btn_close":
            self.dismiss()
