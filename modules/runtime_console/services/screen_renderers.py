from __future__ import annotations

import shutil
from typing import Any

from .models import (
    TABS,
    Palette,
    Snapshot,
    UIState,
    box,
    command_prompt,
    crop,
    fit,
    safe_text,
    tab_strip,
)
from .tab_renderers import (
    _score_bar,
    draw_header,
    draw_sidebar,
    render_actions,
    render_camera,
    render_companion,
    render_config,
    render_expression,
    render_help,
    render_logs,
    render_overview,
    render_right,
    render_search,
    render_signals,
)

__all__ = [
    "_score_bar",
    "draw_header",
    "draw_sidebar",
    "render_actions",
    "render_camera",
    "render_companion",
    "render_config",
    "render_expression",
    "render_help",
    "render_logs",
    "render_main",
    "render_overview",
    "render_right",
    "render_screen",
    "render_search",
    "render_signals",
]


def render_main(
    width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool
) -> list[str]:
    tab_name = TABS[ui.active_tab] if 0 <= ui.active_tab < len(TABS) else "Overview"
    inner_h = height - 2
    if tab_name == "Overview":
        content = render_overview(width, inner_h, snapshot, ui, pal, ascii_mode)
    elif tab_name == "Logs":
        content = render_logs(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Signals":
        content = render_signals(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Config":
        content = render_config(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Search":
        content = render_search(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Actions":
        content = render_actions(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Companion":
        content = render_companion(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Expression":
        content = render_expression(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Camera":
        content = render_camera(width, inner_h, snapshot, ui, pal)
    else:
        content = render_help(width, inner_h, pal)
    return box(
        "WORKSPACE / " + tab_name.upper(),
        [tab_strip(width - 4, ui, pal), ""] + content,
        width,
        height,
        pal,
        ascii_mode,
    )


def render_screen(
    snapshot: Snapshot,
    ui: UIState,
    robot_status: str,
    colors: bool = True,
    ascii_mode: bool = False,
) -> str:
    pal = Palette(colors)
    size = shutil.get_terminal_size((132, 38))
    width = max(96, size.columns)
    height = max(26, size.lines)
    header_h = 2
    footer_h = 3
    body_h = height - header_h - footer_h
    side_w = 26
    right_w = 38 if width >= 126 else 0
    gap = 1
    main_w = width - side_w - right_w - (gap * (2 if right_w else 1))
    out: list[str] = [draw_header(width, snapshot, ui, robot_status, pal)]
    breadcrumb = f" workspace={TABS[ui.active_tab].lower()}  root={crop(str(ui.root), max(10, width - 50))}"
    out.append(fit(pal.dim(breadcrumb), width))
    side = draw_sidebar(body_h, side_w, ui, snapshot, pal, ascii_mode)
    main = render_main(main_w, body_h, snapshot, ui, pal, ascii_mode)
    right = render_right(right_w, body_h, snapshot, ui, pal, ascii_mode) if right_w else []
    for i in range(body_h):
        line = side[i] + " " + main[i]
        if right_w:
            line += " " + right[i]
        out.append(fit(line, width))
    prompt = command_prompt(ui)
    status = f" tab={TABS[ui.active_tab]}  view={ui.log_view}  filter={ui.filter_text or '-'}  selected={ui.selected_event + 1} "
    out.append(fit("-" * width, width))
    out.append(fit(status, width))
    out.append(fit(prompt, width))
    return safe_text("\n".join(out))
