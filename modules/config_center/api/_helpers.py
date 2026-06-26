from __future__ import annotations
from typing import Any
from pathlib import Path
from datetime import datetime
import shutil
import yaml


def read_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_within_repo(p: Path, repo_root: Path) -> bool:
    try:
        p.resolve().relative_to(repo_root)
        return True
    except Exception:
        return False


def backup_file(p: Path) -> None:
    try:
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup = p.with_suffix(p.suffix + f".bak-{ts}")
        shutil.copy2(p, backup)
    except Exception:
        pass


def persist_modules_if_possible(modules, cfg_file_guess: Path) -> None:
    try:
        conf = {}
        if cfg_file_guess.exists():
            conf = yaml.safe_load(cfg_file_guess.read_text(encoding="utf-8")) or {}
        conf["modules"] = modules
        if cfg_file_guess.exists():
            backup_file(cfg_file_guess)
        cfg_file_guess.write_text(
            yaml.safe_dump(conf, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception:
        pass
