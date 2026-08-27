from __future__ import annotations

from pathlib import Path

from modules.runtime_console.tui_v2 import Snapshot, UIState, parse_log_line, project_search, render_screen, strip_ansi


def test_parse_pipe_log_line() -> None:
    ev = parse_log_line("01:19:44 | WARNING  | speak.tts | piper unavailable: model missing")
    assert ev is not None
    assert ev.channel == "TTS"
    assert ev.level == "WARNING"


def test_snapshot_detects_blockers_and_endpoints() -> None:
    snap = Snapshot()
    for line in [
        '01:19:44 | WARNING  | speak.tts | piper unavailable: model missing',
        '01:19:44 | ERROR    | speech.recognizer | SpeechRecognition mic stream failed',
        '01:19:56 | DEBUG    | urllib3.connectionpool | http://127.0.0.1:8080 "GET /vlm/context/latest HTTP/1.1" 200 63',
    ]:
        snap.feed_line(line)
    assert snap.services["TTS"].state == "WARN"
    assert snap.services["AUDIO"].state == "ERR"
    assert snap.endpoints["/vlm/context/latest"] == 1


def test_render_screen_has_opencode_layout(tmp_path: Path) -> None:
    (tmp_path / "run_robot.py").write_text("", encoding="utf-8")
    snap = Snapshot()
    snap.feed_line("01:19:51 | INFO     | agent.orchestrator | LLM provider client ready: google_ai_studio")
    ui = UIState(root=tmp_path)
    text = render_screen(snap, ui, "attached", colors=False, ascii_mode=True)
    plain = strip_ansi(text)
    assert "SENTRYBOT CONTROL CENTER" in plain
    assert "NAVIGATOR" in plain
    assert "WORKSPACE" in plain
    assert "Overview" in plain


def test_render_screen_is_ascii_safe_for_windows_cmd(tmp_path: Path) -> None:
    (tmp_path / "run_robot.py").write_text("", encoding="utf-8")
    snap = Snapshot()
    snap.feed_line("01:33:52 | ERROR    | gateway.bootstrap | STT backend unavailable at C:/Users/emohi/OneDrive/Masaüstü/Project SentryBOT V5 — speech/STT will not work")
    snap.feed_line("â”Œâ”€â”€ bad old border â”‚ WARNING â”‚")
    ui = UIState(root=tmp_path, profile="pc-test")
    text = render_screen(snap, ui, "running pid=123", colors=False, ascii_mode=False)
    assert all(ord(ch) < 128 for ch in text)
    assert "STT" in text or "speech" in text
    assert "+" in text and "-" in text and "|" in text
    assert "â" not in text


def test_project_search(tmp_path: Path) -> None:
    (tmp_path / "run_robot.py").write_text("", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "agent.yaml").write_text("google_ai_studio:\n  api_key: changeme\n", encoding="utf-8")
    results = project_search(tmp_path, "api_key")
    assert results
