from __future__ import annotations

import argparse
import atexit
import os
import sys
import time
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
    KeyReader,
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
    render_overview,
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


def run_tui(
    root: Path,
    run_robot: bool,
    colors: bool,
    ascii_mode: bool,
    no_alt: bool,
    profile: str | None = None,
) -> int:
    force_utf8_stdio()
    enable_virtual_terminal()
    ascii_mode = True if os.environ.get("SENTRYBOT_TUI_UNICODE", "0") != "1" else ascii_mode
    root = root.resolve()
    snapshot = Snapshot()
    detected_profile = "pc-test" if is_pc_test(root) else "robot"
    ui = UIState(root=root, profile=profile or detected_profile)
    tailer = LogTailer(root, start_at_end=run_robot)
    robot = RobotProcess(root, enabled=run_robot, profile=ui.profile)
    ui.message = robot.start()
    alt_on = sys.stdout.isatty() and (not no_alt)
    restored = False

    def restore_terminal() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        try:
            sys.stdout.write("\x1b[?25h")
            if alt_on:
                sys.stdout.write("\x1b[?1049l")
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass

    atexit.register(restore_terminal)
    try:
        if alt_on:
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            sys.stdout.flush()
        with KeyReader() as keys:
            while True:
                if not ui.paused:
                    tailer.read_new(snapshot)
                    request_background_refresh(snapshot, ui)
                key = keys.read()
                handle_key(key, ui, snapshot)
                screen = render_screen(
                    snapshot, ui, robot.status, colors=colors, ascii_mode=ascii_mode
                )
                if alt_on:
                    sys.stdout.write("\x1b[H" + screen)
                else:
                    sys.stdout.write("\x1b[2J\x1b[H" + screen)
                sys.stdout.flush()
                time.sleep(DEFAULT_REFRESH)
    except KeyboardInterrupt:
        ui.message = "stopping"
        return 0
    finally:
        try:
            robot.stop()
        except Exception:
            pass
        restore_terminal()
        try:
            atexit.unregister(restore_terminal)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT opencode-style terminal UI")
    parser.add_argument("--root", default=os.getcwd(), help="SentryBOT project root")
    parser.add_argument("--run", action="store_true", help="start run_robot.py as a subprocess")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--ascii", action="store_true", help="use ASCII borders")
    parser.add_argument(
        "--unicode",
        action="store_true",
        help="allow Unicode borders (not recommended on Windows CMD)",
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
    root = Path(args.root)
    if not (root / "scripts" / "run_robot.py").exists():
        print(f"run_robot.py not found under {root / 'scripts'}", file=sys.stderr)
        return 2
    profile = "pc-test" if args.profile == "pc" else args.profile
    if args.unicode:
        os.environ["SENTRYBOT_TUI_UNICODE"] = "1"
    no_alt = True
    if args.alt:
        no_alt = False
    if args.no_alt:
        no_alt = True
    return run_tui(
        root=root,
        run_robot=args.run,
        colors=not args.no_color,
        ascii_mode=(args.ascii or not args.unicode),
        no_alt=no_alt,
        profile=profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
