from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import LogEvent, Snapshot


class RobotProcess:
    def __init__(self, root: Path, enabled: bool, profile: str | None = None) -> None:
        self.root = root
        self.enabled = enabled
        self.proc: subprocess.Popen[str] | None = None
        self.output_log = root / "logs" / "tui.log"
        self.pid_file = root / "logs" / "sentrybot.pid"
        self.thread: threading.Thread | None = None
        self.profile = str(profile or "")
        atexit.register(self.stop)

    def start(self) -> str:
        if not self.enabled:
            return "attached to existing logs"
        (self.root / "logs").mkdir(exist_ok=True)
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("SENTRYBOT_AUDIO_PROMPT", "0")
        env["SENTRYBOT_CONSOLE_MODE"] = "off"
        env["SENTRYBOT_RUNTIME_CONSOLE"] = "off"
        env["SENTRYBOT_TUI_MODE"] = "1"
        if self.profile in {"pc", "pc-test"}:
            env["SENTRYBOT_PC_TEST"] = "1"
            env["SENTRYBOT_PROFILE"] = "pc-test"
        try:
            if self.output_log.exists():
                prev = self.output_log.with_suffix(".prev.log")
                self.output_log.replace(prev)
        except Exception:
            pass
        cmd = [sys.executable, "-u", "scripts/run_robot.py"]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        try:
            self.pid_file.write_text(str(self.proc.pid), encoding="utf-8")
        except Exception:
            pass
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()
        return "robot subprocess started"

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        with self.output_log.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"\n--- robot subprocess started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            for line in self.proc.stdout:
                fh.write(line)
                fh.flush()

    def stop(self) -> None:
        # Reap an orphaned robot process recorded in the pid file (R58):
        # if the TUI was SIGKILLed, run_robot.py keeps running and the pid
        # file is the only handle to it. Clean it up on the next stop.
        pid_from_file: int | None = None
        try:
            if self.pid_file.exists():
                raw = self.pid_file.read_text(encoding="utf-8").strip()
                pid_from_file = int(raw) if raw.isdigit() else None
        except Exception:
            pid_from_file = None

        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

        if self.proc is None or self.proc.poll() is not None:
            if pid_from_file and pid_from_file != os.getpid():
                try:
                    os.kill(pid_from_file, signal.SIGTERM)
                except Exception:
                    pass
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    @property
    def status(self) -> str:
        if self.proc is None:
            return "attached"
        code = self.proc.poll()
        if code is None:
            return f"running pid={self.proc.pid}"
        return f"stopped code={code}"


def _gateway_base_url() -> str:
    return os.getenv("SENTRYBOT_TUI_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def _json_get(path: str, timeout: float = 0.35) -> tuple[dict[str, Any] | None, str]:
    url = _gateway_base_url() + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(256_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {"value": data}, ""
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(128_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                return data, f"HTTP {exc.code}"
        except Exception:
            pass
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, exc.__class__.__name__ + ": " + str(exc)


def _json_post(
    path: str, payload: dict[str, Any] | None = None, timeout: float = 0.6
) -> tuple[dict[str, Any] | None, str]:
    url = _gateway_base_url() + path
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(256_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {"value": data}, ""
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(128_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                return data, f"HTTP {exc.code}"
        except Exception:
            pass
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, exc.__class__.__name__ + ": " + str(exc)


def refresh_camera_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    if not force and (now - float(snapshot.camera_last_probe or 0.0)) < 2.5:
        return
    snapshot.camera_last_probe = now
    snapshot.camera_probe_url = _gateway_base_url()
    status, err = _json_get("/camera/status")
    if status is not None:
        snapshot.camera_status = status
        snapshot.camera_probe_error = ""
    else:
        snapshot.camera_probe_error = err
    latest, err2 = _json_get("/camera/onsensor/latest")
    if latest is not None:
        snapshot.camera_onsensor = latest
    elif not snapshot.camera_probe_error:
        snapshot.camera_probe_error = err2


def refresh_expression_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    if not force and (now - float(snapshot.expression_last_probe or 0.0)) < 1.5:
        return
    snapshot.expression_last_probe = now
    snapshot.expression_probe_url = _gateway_base_url()
    state, err = _json_get("/expression/state", timeout=0.35)
    if state is not None:
        snapshot.expression_state = state
        snapshot.expression_probe_error = ""
    else:
        snapshot.expression_probe_error = err
    status, err2 = _json_get("/expression/status", timeout=0.35)
    if status is not None:
        snapshot.expression_status = status
    elif not snapshot.expression_probe_error:
        snapshot.expression_probe_error = err2
    history, _ = _json_get("/expression/history?limit=12", timeout=0.35)
    if history is not None:
        snapshot.expression_history = history


def refresh_expression_output_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    last = float(getattr(snapshot, "expression_output_last_probe", 0.0) or 0.0)
    if not force and (now - last) < 1.5:
        return
    snapshot.expression_output_last_probe = now
    status, err = _json_get("/expression/output/status", timeout=0.35)
    if status is not None:
        snapshot.expression_output_status = status
        snapshot.expression_output_probe_error = ""
    else:
        snapshot.expression_output_probe_error = err
    plan, err2 = _json_get("/expression/output/plan", timeout=0.45)
    if plan is not None:
        snapshot.expression_output_plan = plan
        if not snapshot.expression_output_probe_error:
            snapshot.expression_output_probe_error = ""
    elif not snapshot.expression_output_probe_error:
        snapshot.expression_output_probe_error = err2


def _expression_core(snapshot: Snapshot) -> dict[str, Any]:
    state_payload = snapshot.expression_state or {}
    state = state_payload.get("state") if isinstance(state_payload.get("state"), dict) else {}
    status = snapshot.expression_status or {}
    if not state and isinstance(status, dict):
        state = {
            "emotion": status.get("emotion"),
            "arousal": status.get("arousal"),
            "attention": status.get("attention"),
        }
    targets = (
        state_payload.get("targets")
        if isinstance(state_payload.get("targets"), dict)
        else status.get("targets")
        if isinstance(status.get("targets"), dict)
        else {}
    )
    return {"state": state or {}, "targets": targets or {}, "payload": state_payload, "status": status}


def refresh_companion_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    last = float(getattr(snapshot, "companion_last_probe", 0.0) or 0.0)
    if not force and (now - last) < 1.8:
        return
    snapshot.companion_last_probe = now
    snapshot.companion_probe_url = _gateway_base_url()
    needs, err = _json_get("/autonomy/needs", timeout=0.45)
    if needs is not None:
        snapshot.companion_needs = needs
        snapshot.companion_probe_error = ""
    else:
        snapshot.companion_probe_error = err
    goal, err2 = _json_get("/autonomy/goal", timeout=0.45)
    if goal is not None:
        snapshot.companion_goal = goal
        if not snapshot.companion_probe_error:
            snapshot.companion_probe_error = ""
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err2
    execution, err3 = _json_get("/autonomy/goal/execution", timeout=0.45)
    if execution is not None:
        snapshot.companion_execution = execution
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err3
    auto, err4 = _json_get("/autonomy/goal/auto", timeout=0.45)
    if auto is not None:
        snapshot.companion_auto = auto
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err4
    memory, err6 = _json_get("/autonomy/memory", timeout=0.45)
    if memory is not None:
        snapshot.world_memory = memory
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err6
    autowrite, err7 = _json_get("/autonomy/memory/autowrite", timeout=0.45)
    if autowrite is not None:
        snapshot.world_memory_autowrite = autowrite
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err7
    shadow, err8 = _json_get("/autonomy/memory/decision-shadow", timeout=0.45)
    if shadow is not None:
        snapshot.memory_shadow = shadow
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err8
    bias, err9 = _json_get("/autonomy/memory/needs-bias", timeout=0.45)
    if bias is not None:
        snapshot.memory_needs_bias = bias
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err9


def execute_companion_goal_dry_run(snapshot: Snapshot) -> None:
    result, err = _json_post("/autonomy/goal/execute?dry_run=true", {}, timeout=0.8)
    snapshot.companion_probe_url = _gateway_base_url()
    if result is not None:
        snapshot.companion_execution = result
        snapshot.companion_probe_error = ""
        needs, _err = _json_get("/autonomy/needs", timeout=0.35)
        if needs is not None:
            snapshot.companion_needs = needs
        goal, _err2 = _json_get("/autonomy/goal", timeout=0.35)
        if goal is not None:
            snapshot.companion_goal = goal
        auto, _err3 = _json_get("/autonomy/goal/auto", timeout=0.35)
        if auto is not None:
            snapshot.companion_auto = auto
    else:
        snapshot.companion_probe_error = err


def tick_companion_auto_dry_run(snapshot: Snapshot) -> None:
    result, err = _json_post("/autonomy/goal/auto/tick?force=true&dry_run=true", {}, timeout=0.9)
    snapshot.companion_probe_url = _gateway_base_url()
    if result is not None:
        snapshot.companion_auto = result
        execution = result.get("execution") if isinstance(result.get("execution"), dict) else None
        if execution is not None:
            snapshot.companion_execution = execution
        snapshot.companion_probe_error = ""
        needs, _err = _json_get("/autonomy/needs", timeout=0.35)
        if needs is not None:
            snapshot.companion_needs = needs
        goal, _err2 = _json_get("/autonomy/goal", timeout=0.35)
        if goal is not None:
            snapshot.companion_goal = goal
    else:
        snapshot.companion_probe_error = err


def request_background_refresh(snapshot: Snapshot) -> None:
    """Keep gateway probes off the terminal render/input thread."""
    if bool(getattr(request_background_refresh, "running", False)):
        return
    now = time.monotonic()
    last_run = float(getattr(request_background_refresh, "last_run", 0.0) or 0.0)
    if (now - last_run) < 1.0:
        return
    request_background_refresh.running = True
    request_background_refresh.last_run = now

    def _refresh() -> None:
        try:
            refresh_camera_snapshot(snapshot)
            refresh_expression_snapshot(snapshot)
            refresh_expression_output_snapshot(snapshot)
            refresh_companion_snapshot(snapshot)
        except Exception as exc:
            snapshot.feed_event(
                LogEvent(
                    time.strftime("%H:%M:%S"),
                    "WARN",
                    "TUI",
                    "SYS",
                    f"background refresh failed: {exc}",
                    "",
                )
            )
        finally:
            request_background_refresh.running = False

    threading.Thread(target=_refresh, name="sentrybot-tui-refresh", daemon=True).start()
