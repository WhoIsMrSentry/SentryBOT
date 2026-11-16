from __future__ import annotations
import threading
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import APIRouter

from modules.system_control.config_center.api._helpers import persist_modules_if_possible


def get_scan_router(
    modules: list,
    repo_root: Path,
    cfg_file_guess: Path,
    modules_lock: Optional[threading.RLock] = None,
) -> APIRouter:
    r = APIRouter(tags=["config_center-scan"])

    @r.post("/scan")
    def scan_and_register():
        base = repo_root / "modules"
        found: List[Dict[str, str]] = []
        seen_names: set[str] = set()
        for modcfg in sorted(base.rglob("config/config.yml")):
            name = modcfg.parents[1].name
            if name in seen_names:
                continue
            seen_names.add(name)
            rel = str(modcfg.relative_to(repo_root.resolve())).replace("\\", "/")
            found.append({"name": name, "path": rel})

        if modules_lock is not None:
            with modules_lock:
                existing_names = {m.get("name") for m in modules}
                added = [it for it in found if it["name"] not in existing_names]
                modules.extend(added)
                total = len(modules)
        else:
            existing_names = {m.get("name") for m in modules}
            added = [it for it in found if it["name"] not in existing_names]
            modules.extend(added)
            total = len(modules)

        if added:
            persist_modules_if_possible(modules, cfg_file_guess, lock=modules_lock)
        return {"ok": True, "added": added, "total": total}

    return r
