from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, List, Optional
try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None  # type: ignore

import yaml
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, TextArea
from textual.widgets.option_list import Option


LANG_MAP: Dict[str, str] = {
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".py": "python",
    ".toml": "toml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".js": "javascript",
    ".ts": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".ini": "toml",
    ".cfg": "toml",
}

SYNTAX_THEMES: List[tuple[str, str]] = [
    ("Dracula", "dracula"),
    ("Monokai", "monokai"),
    ("VSCode Dark", "vscode_dark"),
    ("GitHub Light", "github_light"),
]


class TabConfig(Widget):
    """Modern Configuration Browser & Multi-Language Syntax-Highlighted Editor."""

    def __init__(self, root: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.config_files: List[Path] = []
        self.filtered_files: List[Path] = []
        self.active_file: Optional[Path] = None
        self.theme_index: int = 0
        self.current_theme: str = SYNTAX_THEMES[0][1]

    def compose(self) -> ComposeResult:
        with Horizontal(id="config_container"):
            # Left side: File List & Search
            with Vertical(id="config_file_tree_container"):
                yield Label("■ CONFIG & CODE REPOSITORY", id="config_tree_title", markup=False)
                yield Input(placeholder="Filter files (yaml, json, py, toml)...", id="config_search_input")
                yield OptionList(id="config_file_list")

            # Right side: Rich Syntax Editor & Tooling
            with Vertical(id="config_editor_container"):
                with Horizontal(id="config_editor_header"):
                    yield Label("No file selected", id="config_file_path_label", markup=False)
                    yield Label("LANG: YAML", id="config_lang_badge", markup=False)
                    yield Button(f"🎨 {SYNTAX_THEMES[self.theme_index][0]}", id="config_theme_btn", variant="default")
                    yield Button("💾 Save Changes", id="config_save_btn", variant="primary")

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
            files.extend(sorted(cfg_dir.glob("*.toml")))

        # Module config directories
        mod_dir = self.root / "modules"
        if mod_dir.exists():
            files.extend(sorted(mod_dir.glob("*/config/*.yaml")))
            files.extend(sorted(mod_dir.glob("*/config/*.yml")))
            files.extend(sorted(mod_dir.glob("*/config/*.json")))
            files.extend(sorted(mod_dir.glob("*/config/*.toml")))
            files.extend(sorted(mod_dir.glob("*/*.yaml")))
            files.extend(sorted(mod_dir.glob("*/*.yml")))

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
            text_area.load_text(content)
        except Exception as exc:
            self.query_one("#config_file_path_label", Label).update(f"Error reading: {exc}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            path = Path(str(event.option_id))
            if path.exists():
                self.load_file(path)

    def cycle_syntax_theme(self) -> None:
        self.theme_index = (self.theme_index + 1) % len(SYNTAX_THEMES)
        theme_name, theme_id = SYNTAX_THEMES[self.theme_index]
        self.current_theme = theme_id
        try:
            btn = self.query_one("#config_theme_btn", Button)
            btn.label = f"🎨 {theme_name}"
            text_area = self.query_one("#config_text_area", TextArea)
            text_area.theme = self.current_theme
            self.notify(f"Syntax Theme: {theme_name}", severity="information", timeout=2.0)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config_save_btn":
            self.save_current_file()
        elif event.button.id == "config_theme_btn":
            self.cycle_syntax_theme()

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
        elif ext == ".py":
            try:
                ast.parse(raw_text)
            except Exception as exc:
                self.notify(f"Python Syntax Error:\n{exc}", severity="error", timeout=6.0)
                return
        elif ext == ".toml" and tomllib is not None:
            try:
                tomllib.loads(raw_text)
            except Exception as exc:
                self.notify(f"TOML Syntax Error:\n{exc}", severity="error", timeout=6.0)
                return

        try:
            with open(self.active_file, "w", encoding="utf-8") as f:
                f.write(raw_text)
            self.notify(f"✔ Successfully saved {self.active_file.name}", severity="information", timeout=3.0)
        except Exception as exc:
            self.notify(f"Failed to save: {exc}", severity="error", timeout=5.0)
