from __future__ import annotations

from ..models import (
    Palette,
    Snapshot,
    UIState,
    fit,
    list_config_files,
    preview_file,
)


def render_config(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    files = list_config_files(ui.root)
    left_w = min(38, max(24, width // 3))
    right_w = width - left_w - 3
    selected = min(max(0, ui.selected_config), max(0, len(files) - 1))
    ui.selected_config = selected
    left: list[str] = [pal.dim("YAML files  (Up/Down select, e edit)")]
    for idx, path in enumerate(files[: max(1, height - 2)]):
        rel = str(path.relative_to(ui.root)).replace("\\", "/")
        line = f"{idx+1:>2} {rel}"
        left.append(pal.cyan(line) if idx == selected else line)
    if not files:
        left.append("no yaml config files found")
    right: list[str] = []
    if files:
        rel = str(files[selected].relative_to(ui.root)).replace("\\", "/")
        right.append(pal.bold(rel))
        right.append(pal.dim("edit: press e, enter dotted.key, enter value"))
        right.append("")
        for i, line in enumerate(preview_file(files[selected], max(0, height - 4)), 1):
            right.append(f"{i:>3} {line}")
    rows = []
    for i in range(height):
        l = fit(left[i] if i < len(left) else "", left_w)
        r = fit(right[i] if i < len(right) else "", right_w)
        rows.append(l + pal.dim(" | ") + r)
    return rows


def render_search(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [
        pal.dim(
            f"query: {ui.project_search or '<none>'}  results:{len(ui.project_results)}  press s to search"
        )
    ]
    lines.append("")
    for res in ui.project_results[: max(0, height - 2)]:
        lines.append(f"{pal.cyan(res.path)}:{res.line}  {res.text}")
    if not ui.project_results and not ui.project_search:
        lines.append("Try: s  piper / vosk / vlm / auth_token / arduino")
    return lines[:height]


def render_actions(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Command workspace"),
        "This screen is intentionally safe for PC testing; it does not assume robot hardware is attached.",
        "",
        pal.bold("Command palette"),
        " :profile pc              classify hardware warnings as expected PC-test gaps",
        " :profile robot           classify hardware warnings as real robot blockers",
        " :filter <text>           filter Logs tab",
        " :view human|full|warn    change Logs view mode",
        " :search <text>           project-wide search",
        " :set <key> <value>       edit selected YAML key from Config tab",
        " :camera refresh          probe /camera/status now",
        " :expression refresh      probe /expression/state now",
        " :expression output       view dry-run output plan",
        " :tab camera             open Camera / IMX500 panel",
        " :quit                    exit TUI",
        "",
        pal.bold("Next engineering phases"),
        " 08 vision request gate: stop unnecessary VLM calls and label true inference vs polls",
        " 09 persistent TTS worker: load Piper once and prevent test-tone-success speech",
        " 10 semantic expression engine: one source for LED/OLED/emotion/motion state",
    ]
    return lines[:height]


def render_help(width: int, height: int, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Navigation"),
        " 1-9             switch workspace tab",
        " Up/Down         move log selection or config file selection",
        " PageUp/PageDn   scroll log viewport",
        " /               filter logs",
        " v               cycle log view: human/full/warn",
        " s               search project files",
        " e               edit selected YAML key in Config",
        " :               command palette",
        " c               clear filter/search/message",
        " r               refresh immediately",
        " q               quit",
        "",
        pal.bold("Layout"),
        " Navigator: sections and health",
        " Workspace: selected tool view",
        " Inspector: selected log/config/event details and suggested fix",
        " Command bar: input and active shortcut state",
        "",
        pal.bold("Logs"),
        " Raw stdout: logs/tui.log",
        " Detailed runtime log: logs/sentry.log",
        " TUI hides polling spam from Overview and groups it in Signals.",
        " Camera tab: live /camera/status and /camera/onsensor/latest diagnostics",
        " Expression tab: live semantic state, targets, event history",
        " Companion tab: needs + semantic goal selector",
        " :execute dry-run current companion goal",
        " :autotick dry-run auto gate tick",
        " :looptick dry-run behavior loop tick",
        " :memory refresh world-memory panel",
        " :memorybias refresh memory shadow/bias",
    ]
    return lines[:height]
