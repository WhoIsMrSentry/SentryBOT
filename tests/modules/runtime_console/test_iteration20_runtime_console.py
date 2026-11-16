from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.arduino_serial.contract_validators import validate_arduino_payload
from modules.cognitive_memory.schema import get_ddl
from modules.runtime_console.api.router import router as console_router
from modules.runtime_console.dashboard import RuntimeConsoleLogHandler
from modules.runtime_console.logwrapper import xLogService
from modules.runtime_console.logwrapper.api.router import router as logs_router
from modules.runtime_console.logwrapper.services.handlers import InMemoryLogHandler, build_formatter
from modules.runtime_console.logwrapper.services.run_rotator import rotate_run_logs
from modules.runtime_console.renderer import ConsoleRenderer
from modules.runtime_console.services.async_gateway_probe import AsyncGatewayProbe
from modules.runtime_console.services.async_log_streamer import AsyncLogStreamer, parse_log_line, format_log_entry_to_rich
from modules.runtime_console.services.async_robot_manager import AsyncRobotManager
from modules.runtime_console.system_info_tui import UIState as SysUIState, render_frame, _ANSI_RE
from modules.runtime_console.themes import CONFIG_PATH
from modules.runtime_console.tui_app import SentryBotApp
from modules.runtime_console import tui_v2
from modules.runtime_console.widgets.modal_memory import MemoryExplorerModal
from modules.runtime_console.widgets.tab_controls import TabControls
from modules.runtime_console.widgets.tab_logs import TabLogs
from modules.runtime_console.services.tui_ascii_helpers import Palette


def _init_sample_cognitive_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    for stmt in get_ddl():
        conn.execute(stmt)
    now = time.time()
    conn.execute(
        """
        INSERT INTO persons (id, canonical_name, display_name, created_at, updated_at)
        VALUES ('p1', 'ali', 'Ali', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO sightings (person_id, ts, source, mood, distance_m)
        VALUES ('p1', ?, 'camera', 'curious', 1.45)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO owner_sessions (start_ts, end_ts, source, authority_level, notes)
        VALUES (?, NULL, 'voice', 9, 'owner active')
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO mood_snapshots (ts, happiness, energy, curiosity, fear, dominant)
        VALUES (?, 0.72, 0.85, 0.91, 0.05, 'curious')
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO world_memories (id, kind, name, summary, source, confidence, salience, observation_count, first_seen, last_seen, location)
        VALUES ('wm_1', 'object', 'CoffeeMug', 'Blue ceramic mug on desk', 'vlm', 0.88, 0.7, 3, ?, ?, 'desk')
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO world_observations (ts, memory_id, source, text)
        VALUES (?, 'wm_1', 'vlm', 'Saw blue mug beside laptop')
        """,
        (now,),
    )
    conn.commit()
    conn.close()


def test_memory_explorer_real_schema_and_world_memory(tmp_path: Path) -> None:
    social_db = tmp_path / "data" / "social.sqlite3"
    _init_sample_cognitive_db(social_db)

    modal = MemoryExplorerModal(root=tmp_path)
    social_text = str(modal._build_social_renderable(query=""))
    assert "Ali" in social_text
    assert "1.45m" in social_text
    assert "ACTIVE" in social_text
    assert "Curious" in social_text
    assert "query note:" not in social_text.lower()

    filtered = str(modal._build_social_renderable(query="Ali"))
    assert "Ali" in filtered

    world_text = str(modal._build_world_memory_renderable(query="Coffee"))
    assert "CoffeeMug" in world_text
    assert "Saw blue mug beside laptop" in world_text
    assert "query note:" not in world_text.lower()

    # Dedicated world_memory.sqlite3 overrides social.sqlite3 fallback when present
    alt_world_db = tmp_path / "data" / "world_memory.sqlite3"
    _init_sample_cognitive_db(alt_world_db)
    world_alt = str(modal._build_world_memory_renderable(query=""))
    assert "world_memory.sqlite3" in world_alt


def test_tab_controls_contracts_and_shared_client(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] | None = None
        if request.content:
            try:
                body = json.loads(request.content.decode("utf-8"))
            except Exception:
                body = None
        calls.append((request.method, request.url.path, body, str(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)))
        if request.url.path == "/agent/step":
            return httpx.Response(404, json={"detail": "Not Found"})
        if request.url.path == "/chat":
            return httpx.Response(200, json={"text": "Merhaba efendim"})
        return httpx.Response(200, json={"ok": True})

    probe = AsyncGatewayProbe("http://test.local:8080")
    probe._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    controls = TabControls(root=tmp_path, gateway_probe=probe)
    logged: list[str] = []
    controls._write_log = lambda msg: logged.append(msg)  # type: ignore[method-assign]

    assert controls._get_http_client() is probe.get_client()

    async def _run() -> None:
        # 1. Stepper contract must use 'pos' (not 'jog')
        await controls.run_stepper_jog_worker.__wrapped__(controls, 120)  # type: ignore[attr-defined]
        # 2. E-STOP hits /state/set/operational with {"value": "estop"}
        await controls.run_estop_worker.__wrapped__(controls)  # type: ignore[attr-defined]
        # 3. Chat fallback hits /chat?query=... instead of /agent/chat
        await controls.run_custom_prompt_worker.__wrapped__(controls, "selam")  # type: ignore[attr-defined]
        await probe.aclose()

    asyncio.run(_run())

    stepper_calls = [c for c in calls if c[1] == "/arduino/request" and (c[2] or {}).get("cmd") == "stepper"]
    assert len(stepper_calls) == 1
    assert validate_arduino_payload(stepper_calls[0][2]) is None
    assert stepper_calls[0][2]["mode"] == "pos"

    op_calls = [c for c in calls if c[1] == "/state/set/operational"]
    assert len(op_calls) == 1
    assert op_calls[0][2] == {"value": "estop"}

    chat_calls = [c for c in calls if c[1] == "/chat"]
    assert len(chat_calls) == 1
    assert "query=selam" in chat_calls[0][3]
    assert not any(c[1] == "/agent/chat" for c in calls)
    assert any("Merhaba efendim" in m for m in logged)


def test_logwrapper_split_files_false_and_no_tui_double_write(tmp_path: Path, monkeypatch) -> None:
    root_logger = logging.getLogger()
    orig_handlers = list(root_logger.handlers)
    orig_memory = xLogService._MEMORY_HANDLER
    rc_logger = logging.getLogger("runtime_console")
    orig_rc_handlers = list(rc_logger.handlers)
    orig_rc_propagate = rc_logger.propagate

    monkeypatch.chdir(tmp_path)
    try:
        # Case 1: separate_files.enabled=False must NOT crash dictConfig
        root_logger.handlers.clear()
        xLogService._MEMORY_HANDLER = None
        xLogService.init_logging(
            {
                "enable_console": False,
                "capture_warnings": False,
                "enable_run_rotation": False,
                "separate_files": {"enabled": False},
            }
        )
        assert xLogService.get_memory_handler() is not None

        for h in root_logger.handlers:
            h.close()
        for h in rc_logger.handlers:
            h.close()

        # Case 2: separate_files.enabled=True must write tui logs ONCE and exclude other modules
        root_logger.handlers.clear()
        rc_logger.handlers.clear()
        xLogService._MEMORY_HANDLER = None
        xLogService.init_logging(
            {
                "enable_console": False,
                "capture_warnings": False,
                "enable_run_rotation": False,
                "separate_files": {
                    "enabled": True,
                    "warnings_path": "logs/warnings.log",
                    "errors_path": "logs/errors.log",
                    "tui_path": "logs/tui.log",
                },
            }
        )
        logging.getLogger("robot.noisy").info("robot-only-line")
        logging.getLogger("runtime_console.ui").info("tui-single-line")
        for h in root_logger.handlers:
            h.flush()
        for h in rc_logger.handlers:
            h.flush()

        tui_content = (tmp_path / "logs" / "tui.log").read_text(encoding="utf-8")
        assert "robot-only-line" not in tui_content
        assert tui_content.count("tui-single-line") == 1
    finally:
        for h in list(root_logger.handlers) + list(rc_logger.handlers):
            h.close()
        root_logger.handlers.clear()
        root_logger.handlers.extend(orig_handlers)
        rc_logger.handlers.clear()
        rc_logger.handlers.extend(orig_rc_handlers)
        rc_logger.propagate = orig_rc_propagate
        xLogService._MEMORY_HANDLER = orig_memory


def test_json_formatter_inmemory_locking_and_log_level_validation() -> None:
    fmt = build_formatter(json_format=True)
    rec = logging.LogRecord(
        name="test.json",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg='Line 1 "quoted"\nLine 2 \\ Turkish: ğüşöçı',
        args=(),
        exc_info=None,
    )
    parsed = json.loads(fmt.format(rec))
    assert parsed["level"] == "INFO"
    assert '"quoted"' in parsed["msg"]
    assert "\n" in parsed["msg"]

    mem = InMemoryLogHandler(maxlen=5)
    mem.setFormatter(fmt)
    mem.emit(rec)
    assert len(mem.tail(5)) == 1
    assert len(list(mem.iter())) == 1
    assert len(mem.tail_struct(5)) == 1
    assert len(list(mem.iter_struct())) == 1

    app = FastAPI()
    assert logs_router is not None
    app.include_router(logs_router)
    client = TestClient(app)

    bad = client.post("/logs/level", json={"logger": "test.level", "level": "BOGUS_LEVEL"})
    assert bad.status_code == 400

    good = client.post("/logs/level", json={"logger": "test.level", "level": "warning"})
    assert good.status_code == 200
    assert logging.getLogger("test.level").level == logging.WARNING


def test_async_robot_manager_stdout_does_not_lock_sentry_log(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    # Keep subprocess alive briefly while parent validates rotation
    (scripts_dir / "run_robot.py").write_text("import time\nprint('robot boot')\ntime.sleep(0.4)\n", encoding="utf-8")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    sentry_log = logs_dir / "sentry.log"
    sentry_log.write_text("previous run log\n", encoding="utf-8")

    mgr = AsyncRobotManager(root=tmp_path, profile="pc-test")

    async def _run() -> None:
        started = await mgr.start()
        assert started is True
        assert mgr.stdout_log_path.name == "runtime_stdout.log"

        # Rotating sentry.log while child stdout handle is open must succeed even on Windows
        archived = rotate_run_logs(logs_dir=logs_dir, max_runs=5)
        assert archived is not None
        assert (archived / "sentry.log").exists()
        assert not sentry_log.exists()

        assert await mgr.restart() is True
        assert mgr.restart_count == 1
        assert await mgr.stop() is True

    asyncio.run(_run())


def test_async_gateway_probe_clears_stale_data_on_offline() -> None:
    online = True

    def handler(request: httpx.Request) -> httpx.Response:
        if not online:
            return httpx.Response(503, json={"ok": False})
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/state/get":
            return httpx.Response(200, json={"operational": "active", "pan": 115.0})
        if request.url.path == "/agent/decision-traces/latest":
            return httpx.Response(200, json={"ok": True, "traces": [{"decision": "greet", "outcome": "success"}]})
        return httpx.Response(404, json={"detail": "missing"})

    probe = AsyncGatewayProbe("http://test.local:8080")
    probe._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def _run() -> None:
        assert await probe.probe_all() is True
        assert probe.state_data.get("pan") == 115.0
        assert len(probe.decision_traces) == 1

        nonlocal online
        online = False
        assert await probe.probe_all() is False
        assert probe.state_data == {}
        assert probe.decision_traces == []
        await probe.aclose()

    asyncio.run(_run())


def test_async_log_streamer_and_tab_logs_export(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "sentry.log").write_text(
        "12:00:00 | INFO     | mod.a | alpha event\n"
        "12:00:01 | ERROR    | mod.b | critical failure happened\n",
        encoding="utf-8",
    )

    tab_logs = TabLogs(root=tmp_path)
    streamer = AsyncLogStreamer(root=tmp_path)
    lines = streamer._read_initial_lines(50)
    for ln in lines:
        entry = parse_log_line(ln)
        tab_logs.add_log_entry(entry, format_log_entry_to_rich(entry))

    tab_logs.active_level_filter = "ERROR"
    exported = tab_logs.export_filtered_logs(export_dir=tmp_path / "exports")
    content = exported.read_text(encoding="utf-8")
    assert "critical failure happened" in content
    assert "alpha event" not in content


def test_themes_lazy_import_and_router_security_and_dashboard_bounds(tmp_path: Path) -> None:
    # 1. Importing themes in isolation must not eagerly import textual
    res = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from modules.runtime_console.themes import get_theme_names, CONFIG_PATH; "
            "assert 'textual' not in sys.modules; assert CONFIG_PATH.is_absolute(); "
            "assert 'sentry-crimson' in get_theme_names()",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, res.stderr
    assert CONFIG_PATH.is_absolute()

    # 2. /runtime_console/events limit validation & auth check
    app = FastAPI()
    app.include_router(console_router)
    client = TestClient(app)
    assert client.get("/runtime_console/events?limit=999").status_code == 422

    # With token set via env
    import os
    old_tok = os.environ.get("SENTRYBOT_RUNTIME_CONSOLE_TOKEN")
    os.environ["SENTRYBOT_RUNTIME_CONSOLE_TOKEN"] = "secret-console-tok"
    try:
        assert client.get("/runtime_console/events?limit=5").status_code == 401
        ok_resp = client.get("/runtime_console/events?limit=5", headers={"X-Auth-Token": "secret-console-tok"})
        assert ok_resp.status_code == 200
    finally:
        if old_tok is None:
            os.environ.pop("SENTRYBOT_RUNTIME_CONSOLE_TOKEN", None)
        else:
            os.environ["SENTRYBOT_RUNTIME_CONSOLE_TOKEN"] = old_tok

    # 3. ConsoleRenderer ASCII mode progress bar
    r = ConsoleRenderer(colors=False, border="ascii")
    bar = r.progress(0.5, width=10)
    assert bar == "#####-----"
    assert all(ord(ch) < 128 for ch in bar)

    # 4. RuntimeConsoleLogHandler._seen stays bounded
    handler = RuntimeConsoleLogHandler(mode="off", aggregate_repeated_messages=False)
    handler._max_seen_entries = 16
    for idx in range(50):
        rec = logging.LogRecord("test.bound", logging.WARNING, __file__, 1, f"msg-{idx}", (), None)
        handler.emit(rec)
    assert len(handler._seen) <= 16


def test_tui_v2_forwards_cli_flags_and_sysinfo_scroll_and_no_fake_defaults(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_robot.py").write_text("", encoding="utf-8")

    captured: dict[str, Any] = {}

    def fake_run_textual_tui(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 0

    import modules.runtime_console.tui_app as tui_app_mod
    monkeypatch.setattr(tui_app_mod, "run_textual_tui", fake_run_textual_tui)

    rc = tui_v2.main(["--root", str(tmp_path), "--no-run", "--ascii", "--no-color", "--no-alt", "--profile", "pc"])
    assert rc == 0
    assert captured["colors"] is False
    assert captured["ascii_mode"] is True
    assert captured["no_alt"] is True
    assert captured["profile"] == "pc-test"

    # System info scroll & ANSI-aware status padding
    pal = Palette(enabled=True)
    state = SysUIState(
        width=60,
        height=6,
        ascii_art=["ART"],
        info_lines=[f"Line {i}" for i in range(15)],
        scroll_offset=3,
    )
    frame = render_frame(state, pal, "#FA1E4E")
    assert "Line 3" in frame[0]
    assert len(_ANSI_RE.sub("", frame[-1])) == 60

    # App accepts ascii_mode / colors flags and exposes restart_count & decision trace handling
    app = SentryBotApp(root=tmp_path, run_robot=False, profile="pc-test", colors=False, ascii_mode=True)
    assert app.ascii_mode is True
    assert app.use_colors is False
    assert app.ansi_color is False
    assert app.robot_manager.restart_count == 0


def test_app_telemetry_tick_na_fallbacks_and_decision_trace_feed(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_robot.py").write_text("", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/state/get":
            # Intentionally minimal real state without fake servo_pan / safety_brake / mic_energy keys
            return httpx.Response(200, json={"operational": "idle", "emotions": ["calm"]})
        if request.url.path == "/autonomy/needs":
            return httpx.Response(200, json={"scores": {"curiosity": 0.4}, "dominant_need": "curiosity", "recommended_goal": "observe_room"})
        if request.url.path == "/agent/decision-traces/latest":
            return httpx.Response(
                200,
                json={"ok": True, "traces": [{"decision": "observe", "outcome": "success", "tool": "look_around", "reason": "curiosity high"}]},
            )
        if request.url.path == "/status":
            return httpx.Response(200, json={"started": ["agent_core", "camera"], "failed": []})
        return httpx.Response(404, json={"detail": "missing"})

    app = SentryBotApp(root=tmp_path, run_robot=False, profile="pc-test", ascii_mode=True)
    app.gateway_probe._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def _run() -> None:
        async with app.run_test():
            await app.periodic_telemetry_tick()
            from textual.widgets import Static

            comp_txt = str(app.query_one("#companion_content", Static).render())
            att_txt = str(app.query_one("#attention_content", Static).render())
            trace_txt = str(app.query_one("#decision_trace_content", Static).render())

            assert "N/A" in comp_txt  # Missing scores show N/A instead of fake 20/45/80/90%
            assert "40%" in comp_txt
            assert "Safety Brake: N/A" in att_txt
            assert "observe_room" in trace_txt
            assert "look_around" in trace_txt
            assert "curiosity high" in trace_txt

    asyncio.run(_run())
