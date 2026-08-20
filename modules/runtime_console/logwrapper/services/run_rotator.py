from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import List, Optional


def rotate_run_logs(
    logs_dir: str | Path = "logs",
    max_runs: int = 5,
    runs_subdir: str = "runs",
) -> Optional[Path]:
    """Archive logs from the previous run into a timestamped directory and retain the last N runs.

    - Creates `logs/runs/run_YYYY-MM-DD_HH-MM-SS/`
    - Moves old logs into the archive folder
    - Purges older run folders beyond `max_runs` (default: 5)
    - Returns the archived path if rotation occurred, else None
    """
    root_logs = Path(logs_dir).resolve()
    if not root_logs.exists():
        root_logs.mkdir(parents=True, exist_ok=True)
        return None

    target_files = [
        "sentry.log",
        "errors.log",
        "warnings.log",
        "tui.log",
        "runtime_stdout.log",
    ]

    existing_files: List[Path] = []
    max_mtime = 0.0
    total_bytes = 0

    for fname in target_files:
        fpath = root_logs / fname
        if fpath.exists() and fpath.is_file():
            st = fpath.stat()
            if st.st_size > 0:
                existing_files.append(fpath)
                total_bytes += st.st_size
                if st.st_mtime > max_mtime:
                    max_mtime = st.st_mtime

    # Also capture numbered or prev backup logs if present in root logs
    for extra in root_logs.glob("*.log.*"):
        if extra.is_file() and extra.stat().st_size > 0:
            existing_files.append(extra)
    for extra in root_logs.glob("*.prev.log"):
        if extra.is_file() and extra.stat().st_size > 0:
            existing_files.append(extra)

    if not existing_files or total_bytes == 0:
        return None

    runs_dir = root_logs / runs_subdir
    runs_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(max_mtime or time.time()))
    archive_folder = runs_dir / f"run_{timestamp_str}"
    
    # Avoid collision if restarted within the same second
    counter = 1
    while archive_folder.exists():
        archive_folder = runs_dir / f"run_{timestamp_str}_{counter}"
        counter += 1

    archive_folder.mkdir(parents=True, exist_ok=True)

    for src in existing_files:
        try:
            dest = archive_folder / src.name
            shutil.move(str(src), str(dest))
        except Exception:
            pass

    # Prune old run folders beyond max_runs
    _prune_old_runs(runs_dir, max_runs=max_runs)

    return archive_folder


def _prune_old_runs(runs_dir: Path, max_runs: int = 5) -> None:
    if not runs_dir.exists():
        return

    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
    run_dirs.sort(key=lambda d: d.name)

    if len(run_dirs) > max_runs:
        to_delete = run_dirs[: len(run_dirs) - max_runs]
        for folder in to_delete:
            try:
                shutil.rmtree(str(folder), ignore_errors=True)
            except Exception:
                pass


__all__ = ["rotate_run_logs"]
