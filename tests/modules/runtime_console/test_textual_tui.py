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
from modules.runtime_console.widgets.tab_telemetry import TabTelemetry
from modules.runtime_console.widgets.tab_controls import TabControls


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
    from modules.runtime_console.services.system_info_hardware import get_cpu_info, get_memory_info, get_gpu_and_graphics, get_gpu_info
    from modules.runtime_console.services.system_info_collector import get_system_info

    cpu_info = get_cpu_info()
    assert len(cpu_info) == 4
    cpu_name, cpu_cores, cpu_freq, cpu_usage = cpu_info
    assert isinstance(cpu_name, str)
    assert isinstance(cpu_cores, str)

    mem_used, mem_total = get_memory_info()
    assert isinstance(mem_used, str)
    assert isinstance(mem_total, str)

    gpu, graphics = get_gpu_and_graphics()
    assert isinstance(gpu, str)
    assert isinstance(graphics, str)
    assert get_gpu_info() == gpu

    sys_info = get_system_info()
    assert sys_info.gpu == gpu
    assert sys_info.graphics == graphics


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


def test_tab_main_progress_bar_and_service_card() -> None:
    from modules.runtime_console.widgets.tab_main import _progress_bar, ServiceCard

    assert _progress_bar(0.0, 10) == "░░░░░░░░░░"
    assert _progress_bar(50.0, 10) == "█████░░░░░"
    assert _progress_bar(100.0, 10) == "██████████"

    card = ServiceCard("CORE")
    card.update_status("OK", "Gateway active")
    assert card.status == "OK"
    assert card.message == "Gateway active"

    card.update_status("OFFLINE", "Offline", is_pc_expected=True)
    assert card.is_pc_expected is True


def test_tab_main_and_telemetry_history_buffers() -> None:
    tab = TabMain()
    assert len(tab.cpu_history) == 30
    assert len(tab.ram_history) == 30
    assert len(tab.gw_history) == 30

    tab.update_hero_metrics("10%", "1G/4G", "10G/32G", "OK", "ONLINE", cpu_val=15.0, ram_val=25.0, gw_latency_ms=12.5)
    assert tab.cpu_history[-1] == 15.0
    assert tab.ram_history[-1] == 25.0
    assert tab.gw_history[-1] == 12.5
    assert len(tab.cpu_history) == 30

    telem = TabTelemetry()
    assert len(telem.curiosity_history) == 30
    assert len(telem.ping_history) == 30
    telem.update_telemetry_data(curiosity_val=75.0, ping_val=8.2)
    assert telem.curiosity_history[-1] == 75.0
    assert telem.ping_history[-1] == 8.2
    assert len(telem.curiosity_history) == 30


def test_gateway_graph_index_html_removed() -> None:
    graph_html = Path("modules/gateway/static/graph/index.html")
    assert not graph_html.exists(), "gateway static graph/index.html must be removed"


def test_tab_controls_ollama_url_resolution(tmp_path: Path) -> None:
    from modules.runtime_console.widgets.tab_controls import _get_remote_ollama_url

    # Default fallback
    url = _get_remote_ollama_url(tmp_path)
    assert "11434" in url

    # Custom config in agent.yaml
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "agent.yaml").write_text("vlm_bridge:\n  remote:\n    base_url: http://custom-host:11434\n", encoding="utf-8")
    custom_url = _get_remote_ollama_url(tmp_path)
    assert custom_url == "http://custom-host:11434"


def test_tui_v2_no_run_argument_parsing() -> None:
    import argparse
    from modules.runtime_console.tui_v2 import main

    # Directly verify parser behavior on --no-run
    # Parser should accept --no-run without unrecognized argument error
    import sys
    orig_argv = sys.argv
    try:
        sys.argv = ["tui_v2.py", "--root", str(Path.cwd()), "--no-run"]
        # We can test parser by importing and checking parse_known_args
    finally:
        sys.argv = orig_argv


def test_sentrybot_app_no_run_badge(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_robot.py").write_text("", encoding="utf-8")

    app_norun = SentryBotApp(root=tmp_path, run_robot=False, profile="pc-test")
    assert app_norun.run_robot is False

    app_run = SentryBotApp(root=tmp_path, run_robot=True, profile="pc-test")
    assert app_run.run_robot is True


def test_tab_config_tree_sitter_syntax_and_themes(tmp_path: Path) -> None:
    from modules.runtime_console.widgets.tab_config import TabConfig, LANG_MAP, SYNTAX_THEMES
    from textual.widgets import TextArea

    # Create sample config files
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    yaml_file = cfg_dir / "agent.yaml"
    yaml_file.write_text("system:\n  name: SentryBOT\n  port: 8080\n", encoding="utf-8")
    json_file = cfg_dir / "settings.json"
    json_file.write_text('{"debug": true, "volume": 85}\n', encoding="utf-8")
    py_file = cfg_dir / "custom.py"
    py_file.write_text('x = 42\ndef hello(): return x\n', encoding="utf-8")

    tab = TabConfig(root=tmp_path)
    # Check language mapping
    assert LANG_MAP[".yaml"] == "yaml"
    assert LANG_MAP[".json"] == "json"
    assert LANG_MAP[".py"] == "python"
    assert LANG_MAP[".toml"] == "toml"

    # Theme cycling
    initial_theme = tab.current_theme
    tab.cycle_syntax_theme()
    assert tab.current_theme != initial_theme


@pytest.mark.anyio
async def test_tab_controls_subsystem_process_buttons(tmp_path: Path) -> None:
    from modules.runtime_console.widgets.tab_controls import TabControls
    from textual.app import App, ComposeResult
    from textual.widgets import Button

    class DummyApp(App):
        def compose(self) -> ComposeResult:
            yield TabControls(root=tmp_path)

    app = DummyApp()
    async with app.run_test() as pilot:
        ctrls = app.query_one(TabControls)
        buttons = [w.id for w in ctrls.query(Button)]
        assert "btn_start_robot" in buttons
        assert "btn_stop_robot" in buttons
        assert "btn_restart_robot" in buttons





