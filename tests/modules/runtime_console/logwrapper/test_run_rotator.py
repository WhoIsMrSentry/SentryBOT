import tempfile
import time
from pathlib import Path
from modules.runtime_console.logwrapper.services.run_rotator import rotate_run_logs


def test_rotate_run_logs_empty_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir)
        archived = rotate_run_logs(logs_dir=logs_dir, max_runs=5)
        assert archived is None


def test_rotate_run_logs_moves_files_and_prunes_older_runs():
    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir)
        # Create mock run files
        sentry_log = logs_dir / "sentry.log"
        sentry_log.write_text("log line 1\n", encoding="utf-8")
        err_log = logs_dir / "errors.log"
        err_log.write_text("error line\n", encoding="utf-8")

        archived = rotate_run_logs(logs_dir=logs_dir, max_runs=2)
        assert archived is not None
        assert archived.exists()
        assert (archived / "sentry.log").exists()
        assert (archived / "errors.log").exists()
        assert not sentry_log.exists()

        # Simulate multiple subsequent runs to test pruning to max_runs=2
        runs_dir = logs_dir / "runs"
        # Manually create mock run folders
        (runs_dir / "run_2026-01-01_10-00-00").mkdir(parents=True, exist_ok=True)
        (runs_dir / "run_2026-01-02_10-00-00").mkdir(parents=True, exist_ok=True)
        (runs_dir / "run_2026-01-03_10-00-00").mkdir(parents=True, exist_ok=True)

        # Trigger another rotation
        sentry_log.write_text("new log\n", encoding="utf-8")
        archived2 = rotate_run_logs(logs_dir=logs_dir, max_runs=2)
        assert archived2 is not None

        remaining_runs = [d.name for d in runs_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
        assert len(remaining_runs) == 2
