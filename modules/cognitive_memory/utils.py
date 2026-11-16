"""Shared helpers for SQLite path resolution, exponential salience decay, and hot backups."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_repo_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return (project_root() / p).resolve()


def decay_salience(score: float, elapsed_s: float, half_life_s: float = 216000.0) -> float:
    """Apply true exponential half-life decay to a [0, 1] salience score."""
    dt = max(0.0, float(elapsed_s))
    hl = max(1.0, float(half_life_s))
    factor = 0.5 ** (dt / hl)
    return max(0.0, min(1.0, float(score) * factor))


def backup_sqlite_connection(src_conn: sqlite3.Connection, lock: Any, dest_path: str | Path) -> Path:
    """Safely back up an open SQLite database online using Connection.backup() + atomic replace."""
    target = Path(dest_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    with lock:
        dst = sqlite3.connect(str(tmp_path))
        try:
            src_conn.backup(dst)
            dst.commit()
        finally:
            dst.close()
    os.replace(tmp_path, target)
    return target
