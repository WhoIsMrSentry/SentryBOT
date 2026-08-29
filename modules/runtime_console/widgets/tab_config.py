from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Select, TextArea
from textual.widgets.option_list import Option


LANG_MAP: Dict[str, str] = {
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".py": "python",
    ".toml": "toml",
    ".md": "markdown",
    ".sh": "bash",
    ".sql": "sql",
    ".ini": "toml",
    ".cfg": "toml",
}

THEME_CHOICES = [
    ("Dracula Crimson", "dracula"),
    ("Monokai High-Contrast", "monokai"),
    ("VSCode Dark", "vscode_dark"),
    ("GitHub Dark", "github_light"),
]


class TabConfig(Widget):
    """Modern Configuration Browser & Multi-Language Syntax-Highlighted Editor."""

    def __init__(self, root: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.config_files: List[Path] = []
        self.filtered_files: List[Path] = []
        self.active_file: Optional[Path] = None
        self.current_theme = "dracula"

    def compose(self) -> ComposeResult:
        with Horizontal(id="config_container"):
            # Left side: File List & Search
            with Vertical(id="config_file_tree_container"):
                yield Label("[ CONFIG FILES ]", id="config_tree_title", markup=False)
                yield Input(placeholder="Search config file...", id="config_search_input")
                yield OptionList(id="config_file_list")

            # Right side: Rich Syntax Editor & Tooling
            with Vertical(id="config_editor_container"):
                with Horizontal(id="config_editor_header"):
                    yield Label("No file selected", id="config_file_path_label", markup=False)
                    yield Label("LANG: YAML", id="config_lang_badge", markup=False)
                    yield Button("Save Changes", id="config_save_btn", variant="primary")

                yield TextArea(
                    "",
                    id="config_text_area",
                    language="yaml",
                    theme=self.current_theme,
                    show_line_numbers=True,
                    read_only=False,
                )

    def on_mount(self) -> None:
        self.scan_config_files()

    def scan_config_files(self) -> None:
        files: List[Path] = []
        # Main config directory
        cfg_dir = self.root / "config"
        if cfg_dir.exists():
            files.extend(sorted(cfg_dir.glob("*.yaml")))
            files.extend(sorted(cfg_dir.glob("*.yml")))
            files.extend(sorted(cfg_dir.glob("*.json")))

        # Module config directories
        mod_dir = self.root / "modules"
        if mod_dir.exists():
            files.extend(sorted(mod_dir.glob("*/config/*.yaml")))
            files.extend(sorted(mod_dir.glob("*/config/*.yml")))
            files.extend(sorted(mod_dir.glob("*/config/*.json")))
            files.extend(sorted(mod_dir.glob("*/*.yaml")))

        self.config_files = sorted(list(set(files)))
        self.filtered_files = list(self.config_files)
        self._populate_file_list()

    def _populate_file_list(self) -> None:
        try:
            opt_list = self.query_one("#config_file_list", OptionList)
            opt_list.clear_options()
            for path in self.filtered_files:
                try:
                    rel = str(path.relative_to(self.root)).replace("\\", "/")
                except ValueError:
                    rel = path.name
                opt_list.add_option(Option(prompt=rel, id=str(path)))

            if self.filtered_files and self.active_file is None:
                opt_list.highlighted = 0
                self.load_file(self.filtered_files[0])
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "config_search_input":
            query = event.value.strip().lower()
            if not query:
                self.filtered_files = list(self.config_files)
            else:
                self.filtered_files = [
                    p for p in self.config_files
                    if query in str(p).lower()
                ]
            self._populate_file_list()

    def load_file(self, path: Path) -> None:
        self.active_file = path
        try:
            try:
                rel = str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel = path.name

            ext = path.suffix.lower()
            detected_lang = LANG_MAP.get(ext, "yaml")

            self.query_one("#config_file_path_label", Label).update(f"Editing: {rel}")
            self.query_one("#config_lang_badge", Label).update(f"LANG: {detected_lang.upper()}")
            
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            text_area = self.query_one("#config_text_area", TextArea)
            text_area.language = detected_lang
            text_area.theme = self.current_theme
            text_area.text = content
        except Exception as exc:
            self.query_one("#config_file_path_label", Label).update(f"Error reading: {exc}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            path = Path(str(event.option_id))
            if path.exists():
                self.load_file(path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config_save_btn":
            self.save_current_file()

    def save_current_file(self) -> None:
        if not self.active_file or not self.active_file.exists():
            self.notify("No active file to save!", severity="warning")
            return

        text_area = self.query_one("#config_text_area", TextArea)
        raw_text = text_area.text
        ext = self.active_file.suffix.lower()

        # Validate syntax based on file type before saving
        if ext in [".yaml", ".yml"]:
            try:
                yaml.safe_load(raw_text)
            except Exception as exc:
                self.notify(f"YAML Syntax Error:\n{exc}", severity="error", timeout=6.0)
                return
        elif ext == ".json":
            try:
                json.loads(raw_text)
            except Exception as exc:
                self.notify(f"JSON Syntax Error:\n{exc}", severity="error", timeout=6.0)
                return

        try:
            with open(self.active_file, "w", encoding="utf-8") as f:
                f.write(raw_text)
            self.notify(f"✔ Successfully saved {self.active_file.name}", severity="information", timeout=3.0)
        except Exception as exc:
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5.0)
