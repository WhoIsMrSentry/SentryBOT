from __future__ import annotations

import asyncio
from pathlib import Path
import pytest
from rich.text import Text

from modules.runtime_console.services.async_log_streamer import AsyncLogStreamer, parse_log_line, format_log_entry_to_rich
from modules.runtime_console.services.async_robot_manager import AsyncRobotManager
from modules.runtime_console.services.async_gateway_probe import AsyncGatewayProbe
from modules.runtime_console.tui_app import SentryBotApp
from modules.runtime_console.widgets.tab_main import TabMain
from modules.runtime_console.widgets.tab_logs import TabLogs
from modules.runtime_console.widgets.tab_config import TabConfig


def test_parse_log_line_levels() -> None:
    entry_info = parse_log_line("2026-08-29 19:55:00 [INFO] [sentrybot.core] Runtime started")
    assert entry_info.level == "INFO"
    assert entry_info.logger == "sentrybot.core"
    assert "Runtime started" in entry_info.message

    entry_warn = parse_log_line("01:20:15 WARNING [speak.tts] Piper model missing")
    assert entry_warn.level == "WARN"
    assert "Piper model missing" in entry_warn.message

    entry_err = parse_log_line("[ERROR] [speech] Mic stream failed")
    assert entry_err.level == "ERROR"


def test_format_log_entry_to_rich() -> None:
    entry = parse_log_line("12:00:00 [ERROR] [ai.llm] Connection refused")
    rich_text = format_log_entry_to_rich(entry)
    assert isinstance(rich_text, Text)
    assert "ERROR" in rich_text.plain
    assert "Connection refused" in rich_text.plain


def test_async_robot_manager_init(tmp_path: Path) -> None:
    async def _test() -> None:
        mgr = AsyncRobotManager(tmp_path, profile="pc-test")
        assert not mgr.is_running
        assert mgr.pid is None
        assert mgr.uptime_str == "00:00"
        assert mgr.check_liveness() == "STOPPED"

    asyncio.run(_test())


def test_async_gateway_probe_offline() -> None:
    async def _test() -> None:
        probe = AsyncGatewayProbe("http://127.0.0.1:59999")
        online = await probe.probe_all()
        assert not online
        assert probe.error_message is not None

    asyncio.run(_test())


def test_sentrybot_app_instance(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_robot.py").write_text("", encoding="utf-8")
    app = SentryBotApp(root=tmp_path, run_robot=False, profile="pc-test")
    assert app.TITLE == "SentryBOT Control Center"
    assert app.profile == "pc-test"
    assert app.theme == "sentry-crimson"


def test_theme_registry_and_switching() -> None:
    from modules.runtime_console.themes import THEMES, get_theme_names, get_theme
    names = get_theme_names()
    assert "sentry-crimson" in names
    assert "posting" in names
    assert "nord" in names
    assert "dracula" in names
    assert "matrix" in names

    crimson = get_theme("sentry-crimson")
    assert crimson.primary == "#FA1E4E"
    assert crimson.secondary == "#88001b"


def test_system_info_hardware_unpacking() -> None:
    from modules.runtime_console.services.system_info_hardware import get_cpu_info, get_memory_info
    cpu_info = get_cpu_info()
    assert len(cpu_info) == 4
    cpu_name, cpu_cores, cpu_freq, cpu_usage = cpu_info
    assert isinstance(cpu_name, str)
    assert isinstance(cpu_cores, str)

    mem_used, mem_total = get_memory_info()
    assert isinstance(mem_used, str)
    assert isinstance(mem_total, str)


def test_all_themes_compile_stylesheet(tmp_path: Path) -> None:
    from textual.css.stylesheet import Stylesheet
    app = SentryBotApp(root=tmp_path, run_robot=False)
    css_file = Path("modules/runtime_console/sentrybot.tcss")
    content = css_file.read_text(encoding="utf-8")

    for theme_name in app.available_themes.keys():
        app.theme = theme_name
        vars = app.get_css_variables()
        ss = Stylesheet(variables=vars)
        ss.add_source(content, str(css_file))
        ss.parse()
        assert len(ss.rules) > 50


def test_new_tabs_instantiation(tmp_path: Path) -> None:
    from modules.runtime_console.widgets.tab_telemetry import TabTelemetry
    from modules.runtime_console.widgets.tab_controls import TabControls

    telem = TabTelemetry()
    assert telem is not None

    ctrls = TabControls(root=tmp_path)
    assert ctrls is not None



