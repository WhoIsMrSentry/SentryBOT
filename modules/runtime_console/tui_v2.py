from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .services import (
    ANSI_RE,
    APP,
    ASCII_TRANSLATION,
    BLOCKER_HINTS,
    CHANNEL_HINTS,
    COMPACT_RE,
    DEFAULT_REFRESH,
    HTTP_RE,
    LEVEL_ORDER,
    LOG_RE,
    MAX_SEARCH_FILE_BYTES,
    MAX_TAIL_BYTES,
    NOISE_HINTS,
    PC_EXPECTED_HINTS,
    REMOTE_RE,
    RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT,
    RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE,
    SEARCH_EXTS,
    SERVICE_RULES,
    TABS,
    TITLE,
    VERSION,
    LogEvent,
    LogTailer,
    Palette,
    RobotProcess,
    SearchResult,
    ServiceStatus,
    Snapshot,
    UIState,
    border_chars,
    box,
    clean_path,
    command_prompt,
    crop,
    current_log_events,
    dict_get,
    draw_header,
    draw_sidebar,
    edit_yaml,
    enable_virtual_terminal,
    event_is_pc_expected,
    event_line,
    events_for_view,
    execute_companion_goal_dry_run,
    filter_events,
    fit,
    force_utf8_stdio,
    handle_command,
    handle_key,
    hbar,
    health_summary_for,
    infer_channel,
    is_low_value_startup,
    is_pc_expected,
    is_pc_test,
    list_config_files,
    newest_first_events,
    parse_log_line,
    parse_scalar,
    preview_file,
    project_search,
    refresh_camera_snapshot,
    refresh_companion_snapshot,
    refresh_expression_output_snapshot,
    refresh_expression_snapshot,
    render_actions,
    render_camera,
    render_companion,
    render_config,
    render_expression,
    render_help,
    render_logs,
    render_main,
    render_right,
    render_screen,
    render_search,
    render_signals,
    repair_mojibake,
    request_background_refresh,
    safe_text,
    selected_event,
    service_card,
    service_is_pc_expected,
    set_nested,
    strip_ansi,
    suggested_fix,
    tab_strip,
    tick_companion_auto_dry_run,
    visible_len,
    yes_no,
)
from .tui_app import SentryBotApp, run_textual_tui


def run_tui(
    root: Path,
    run_robot: bool,
    colors: bool = True,
    ascii_mode: bool = False,
    no_alt: bool = False,
    profile: str | None = None,
) -> int:
    """Launch the modern Textual SentryBOT Control Center."""
    return run_textual_tui(
        root=root,
        run_robot=run_robot,
        profile=profile,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT Modern Control Center TUI")
    parser.add_argument("--root", default=os.getcwd(), help="SentryBOT project root")
    parser.add_argument("--run", action="store_true", help="start run_robot.py as a subprocess")
    parser.add_argument("--no-run", action="store_true", help="show the TUI without starting robot services")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--ascii", action="store_true", help="use ASCII borders")
    parser.add_argument(
        "--unicode",
        action="store_true",
        help="allow Unicode borders",
    )
    parser.add_argument("--no-alt", action="store_true", help="do not use terminal alternate screen")
    parser.add_argument("--alt", action="store_true", help="use terminal alternate screen")
    parser.add_argument(
        "--profile",
        choices=["pc", "pc-test", "robot"],
        default=None,
        help="override detected runtime profile",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not (root / "scripts" / "run_robot.py").exists():
        print(f"run_robot.py not found under {root / 'scripts'}", file=sys.stderr)
        return 2

    profile = "pc-test" if args.profile == "pc" else args.profile
    should_run_robot = bool(args.run) and not bool(args.no_run)
    return run_tui(
        root=root,
        run_robot=should_run_robot,
        profile=profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
