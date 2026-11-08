from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from fastapi import Response
import yaml


def read_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_within_repo(p: Path, repo_root: Path) -> bool:
    try:
        p.resolve().relative_to(repo_root.resolve())
        return True
    except Exception:
        return False


def resolve_module_config_path(
    modules: list,
    module: str,
    repo_root: Path,
    lock: Optional[threading.RLock] = None,
) -> Tuple[Optional[Path], Optional[Response]]:
    """Lookup a registered module config path and validate workspace containment."""
    if lock is not None:
        with lock:
            item = next((m for m in modules if m.get("name") == module), None)
            raw_path = item.get("path") if item else None
    else:
        item = next((m for m in modules if m.get("name") == module), None)
        raw_path = item.get("path") if item else None

    if not item:
        return None, Response(status_code=404, content="module not found")
    if not raw_path:
        return None, Response(status_code=404, content="path not set")

    p = Path(str(raw_path))
    if not p.is_absolute():
        p = (repo_root / raw_path).resolve()
    else:
        p = p.resolve()
    if not is_within_repo(p, repo_root):
        return None, Response(status_code=403, content="path outside workspace")
    return p, None


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically write UTF-8 text via a same-directory temporary file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def list_backups(p: Path) -> List[Path]:
    """Return existing backup files for ``p`` ordered newest first."""
    return sorted(p.parent.glob(f"{p.name}.bak-*"), reverse=True)


def backup_file(p: Path, keep: int = 5) -> Optional[Path]:
    """Copy ``p`` to a timestamped ``.bak-*`` sibling and prune backups older than ``keep``."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        backup = p.with_name(f"{p.name}.bak-{ts}")
        shutil.copy2(p, backup)
        if keep > 0:
            for stale in list_backups(p)[keep:]:
                stale.unlink(missing_ok=True)
        return backup
    except Exception:
        return None


def persist_modules_if_possible(
    modules: list,
    cfg_file_guess: Path,
    lock: Optional[threading.RLock] = None,
) -> None:
    try:
        if lock is not None:
            with lock:
                modules_copy = [dict(m) for m in modules]
        else:
            modules_copy = [dict(m) for m in modules]

        conf = {}
        if cfg_file_guess.exists():
            conf = yaml.safe_load(cfg_file_guess.read_text(encoding="utf-8")) or {}
        conf["modules"] = modules_copy
        if cfg_file_guess.exists():
            backup_file(cfg_file_guess)
        atomic_write_text(
            cfg_file_guess,
            yaml.safe_dump(conf, sort_keys=False, allow_unicode=True),
        )
    except Exception:
        pass
