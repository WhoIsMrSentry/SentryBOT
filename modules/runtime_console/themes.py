from __future__ import annotations

from pathlib import Path
from typing import Dict, List
from textual.theme import Theme

# SentryBOT Built-in Themes (Including Posting, Crimson, Cyberpunk, Nord, Dracula, etc.)
THEMES: Dict[str, Theme] = {
    "sentry-crimson": Theme(
        name="sentry-crimson",
        primary="#FA1E4E",
        secondary="#88001b",
        accent="#FA1E4E",
        warning="#FFB300",
        error="#FF1744",
        success="#00E676",
        background="#0a0306",
        surface="#14060b",
        panel="#1c0810",
        foreground="#ffffff",
        variables={
            "border-color": "#88001b",
            "border-active": "#FA1E4E",
            "card-bg": "#14060b",
            "card-hover": "#220c15",
            "text-highlight": "#FA1E4E",
            "hero-bg": "#18070e",
        },
    ),
    "posting": Theme(
        name="posting",
        primary="#458588",
        secondary="#b16286",
        accent="#8ec07c",
        warning="#fabd2f",
        error="#fb4934",
        success="#b8bb26",
        background="#1d2021",
        surface="#282828",
        panel="#32302f",
        foreground="#ebdbb2",
        variables={
            "border-color": "#3c3836",
            "border-active": "#83a598",
            "card-bg": "#282828",
            "card-hover": "#3c3836",
            "text-highlight": "#83a598",
            "hero-bg": "#282828",
        },
    ),
    "nord": Theme(
        name="nord",
        primary="#88c0d0",
        secondary="#81a1c1",
        accent="#8fbcbb",
        warning="#ebcb8b",
        error="#bf616a",
        success="#a3be8c",
        background="#242933",
        surface="#2e3440",
        panel="#3b4252",
        foreground="#eceff4",
        variables={
            "border-color": "#434c5e",
            "border-active": "#88c0d0",
            "card-bg": "#2e3440",
            "card-hover": "#3b4252",
            "text-highlight": "#88c0d0",
            "hero-bg": "#2e3440",
        },
    ),
    "monokai": Theme(
        name="monokai",
        primary="#a6e22e",
        secondary="#f92672",
        accent="#66d9ef",
        warning="#fd971f",
        error="#f92672",
        success="#a6e22e",
        background="#1e1f1c",
        surface="#272822",
        panel="#383830",
        foreground="#f8f8f2",
        variables={
            "border-color": "#49483e",
            "border-active": "#a6e22e",
            "card-bg": "#272822",
            "card-hover": "#383830",
            "text-highlight": "#a6e22e",
            "hero-bg": "#272822",
        },
    ),
    "dracula": Theme(
        name="dracula",
        primary="#bd93f9",
        secondary="#ff79c6",
        accent="#50fa7b",
        warning="#f1fa8c",
        error="#ff5555",
        success="#50fa7b",
        background="#1e1f29",
        surface="#282a36",
        panel="#343746",
        foreground="#f8f8f2",
        variables={
            "border-color": "#44475a",
            "border-active": "#bd93f9",
            "card-bg": "#282a36",
            "card-hover": "#44475a",
            "text-highlight": "#ff79c6",
            "hero-bg": "#282a36",
        },
    ),
    "tokyo-night": Theme(
        name="tokyo-night",
        primary="#7aa2f7",
        secondary="#bb9af7",
        accent="#7dcfff",
        warning="#e0af68",
        error="#f7768e",
        success="#9ece6a",
        background="#16161e",
        surface="#1a1b26",
        panel="#24283b",
        foreground="#c0caf5",
        variables={
            "border-color": "#292e42",
            "border-active": "#7aa2f7",
            "card-bg": "#1a1b26",
            "card-hover": "#24283b",
            "text-highlight": "#7aa2f7",
            "hero-bg": "#1a1b26",
        },
    ),
    "cyberpunk": Theme(
        name="cyberpunk",
        primary="#ffe600",
        secondary="#ff003c",
        accent="#00e5ff",
        warning="#ffe600",
        error="#ff003c",
        success="#00ff66",
        background="#05070a",
        surface="#0e131d",
        panel="#161c2b",
        foreground="#e0f7fa",
        variables={
            "border-color": "#ff003c",
            "border-active": "#ffe600",
            "card-bg": "#0e131d",
            "card-hover": "#1a2234",
            "text-highlight": "#ffe600",
            "hero-bg": "#0e131d",
        },
    ),
    "catppuccin": Theme(
        name="catppuccin",
        primary="#89b4fa",
        secondary="#f5c2e7",
        accent="#a6e3a1",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
        background="#11111b",
        surface="#1e1e2e",
        panel="#313244",
        foreground="#cdd6f4",
        variables={
            "border-color": "#45475a",
            "border-active": "#89b4fa",
            "card-bg": "#1e1e2e",
            "card-hover": "#313244",
            "text-highlight": "#f5c2e7",
            "hero-bg": "#1e1e2e",
        },
    ),
    "matrix": Theme(
        name="matrix",
        primary="#00ff66",
        secondary="#008f39",
        accent="#00ff99",
        warning="#ffff00",
        error="#ff3333",
        success="#00ff66",
        background="#030804",
        surface="#061208",
        panel="#0a1c0d",
        foreground="#b8ffc8",
        variables={
            "border-color": "#005522",
            "border-active": "#00ff66",
            "card-bg": "#061208",
            "card-hover": "#0e2a14",
            "text-highlight": "#00ff66",
            "hero-bg": "#061208",
        },
    ),
    "solarized-dark": Theme(
        name="solarized-dark",
        primary="#268bd2",
        secondary="#2aa198",
        accent="#859900",
        warning="#b58900",
        error="#dc322f",
        success="#859900",
        background="#00212b",
        surface="#002b36",
        panel="#073642",
        foreground="#839496",
        variables={
            "border-color": "#073642",
            "border-active": "#268bd2",
            "card-bg": "#002b36",
            "card-hover": "#073642",
            "text-highlight": "#2aa198",
            "hero-bg": "#002b36",
        },
    ),
}

DEFAULT_THEME_NAME = "sentry-crimson"
CONFIG_PATH = Path("config/tui_theme.txt")


def get_saved_theme_name() -> str:
    try:
        if CONFIG_PATH.exists():
            name = CONFIG_PATH.read_text(encoding="utf-8").strip()
            if name in THEMES:
                return name
    except Exception:
        pass
    return DEFAULT_THEME_NAME


def save_theme_name(name: str) -> None:
    if name in THEMES:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(name, encoding="utf-8")
        except Exception:
            pass


def get_theme_names() -> List[str]:
    return list(THEMES.keys())


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME_NAME])
