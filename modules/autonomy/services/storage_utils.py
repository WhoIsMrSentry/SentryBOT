"""Shared path resolution and locked atomic JSON file persistence helpers for autonomy services."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_autonomy_path(raw_path: Any, default_rel: str) -> Path:
    """Resolve a configured data path relative to the repository root when non-absolute."""
    candidate = Path(str(raw_path or default_rel))
    if not candidate.is_absolute():
        candidate = _REPO_ROOT / candidate
    return candidate


def atomic_write_json(path: Path, data: Any, lock: Optional[threading.RLock] = None) -> None:
    """Atomically write JSON via same-directory temp file and os.replace."""
    text = json.dumps(data, ensure_ascii=False, indent=2)

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass
            raise

    if lock is not None:
        with lock:
            _write()
    else:
        _write()


def read_json_dict(
    path: Path,
    default_factory: Callable[[], Dict[str, Any]],
    lock: Optional[threading.RLock] = None,
) -> Dict[str, Any]:
    """Read a JSON object safely under lock, returning a fresh fallback dict on error."""

    def _read() -> Dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else default_factory()
        except Exception:
            return default_factory()

    if lock is not None:
        with lock:
            return _read()
    return _read()


__all__ = ["resolve_autonomy_path", "atomic_write_json", "read_json_dict"]
