from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class AsyncRobotManager:
    """Non-blocking robot process supervisor for SentryBOT."""

    def __init__(self, root: Path, profile: str = "pc-test") -> None:
        self.root = root
        self.profile = profile
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.started_at: Optional[float] = None
        self.last_status = "STOPPED"
        self.last_error = ""
        self._stdout_file = None

    @property
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        if self.is_running and self.process:
            return self.process.pid
        return None

    @property
    def uptime_seconds(self) -> float:
        if self.is_running and self.started_at:
            return time.time() - self.started_at
        return 0.0

    @property
    def uptime_str(self) -> str:
        s = int(self.uptime_seconds)
        mins, secs = divmod(s, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    async def start(self) -> bool:
        if self.is_running:
            return True

        runner = self.root / "scripts" / "run_robot.py"
        if not runner.exists():
            self.last_error = f"Runner script not found: {runner}"
            self.last_status = "ERROR"
            return False

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if self.profile == "pc-test":
            env["SENTRYBOT_PROFILE"] = "pc-test"
            env["SENTRYBOT_ALLOW_PC_FALLBACK"] = "1"
        else:
            env["SENTRYBOT_PROFILE"] = "robot"
            # WSL or x86 host fallback fallback safety
            if os.name == "nt" or not Path("/proc/device-tree/model").exists():
                env["SENTRYBOT_ALLOW_PC_FALLBACK"] = "1"

        logs_dir = self.root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = logs_dir / "sentry.log"
        try:
            self._stdout_file = open(log_file_path, "a", encoding="utf-8")
        except Exception:
            self._stdout_file = None

        stdout_target = self._stdout_file if self._stdout_file else subprocess.DEVNULL
        stderr_target = subprocess.STDOUT if self._stdout_file else subprocess.DEVNULL

        python_bin = sys.executable
        try:
            self.process = subprocess.Popen(
                [python_bin, str(runner)],
                cwd=str(self.root),
                env=env,
                stdout=stdout_target,
                stderr=stderr_target,
                stdin=subprocess.DEVNULL,
            )
            self.started_at = time.time()
            self.last_status = "RUNNING"
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.last_status = "CRASHED"
            if self._stdout_file:
                try:
                    self._stdout_file.close()
                except Exception:
                    pass
                self._stdout_file = None
            return False

    async def stop(self, timeout_s: float = 3.0) -> bool:
        if not self.is_running or not self.process:
            self.last_status = "STOPPED"
            self.started_at = None
            if self._stdout_file:
                try:
                    self._stdout_file.close()
                except Exception:
                    pass
                self._stdout_file = None
            return True

        try:
            if os.name == "nt":
                # Windows graceful terminate
                self.process.terminate()
            else:
                self.process.send_signal(signal.SIGINT)

            # Wait asynchronously
            start = time.time()
            while time.time() - start < timeout_s:
                if self.process.poll() is not None:
                    break
                await asyncio.sleep(0.1)

            if self.process.poll() is None:
                self.process.kill()
                await asyncio.sleep(0.1)

            self.last_status = "STOPPED"
            self.started_at = None
            if self._stdout_file:
                try:
                    self._stdout_file.close()
                except Exception:
                    pass
                self._stdout_file = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    async def restart(self) -> bool:
        await self.stop()
        await asyncio.sleep(0.5)
        return await self.start()

    def check_liveness(self) -> str:
        if self.process is None:
            return "STOPPED"
        code = self.process.poll()
        if code is None:
            self.last_status = "RUNNING"
            return "RUNNING"
        if code == 0:
            self.last_status = "STOPPED"
            self.started_at = None
            return "STOPPED"
        self.last_status = "CRASHED"
        self.started_at = None
        return f"CRASHED (code {code})"
