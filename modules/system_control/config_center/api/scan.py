from __future__ import annotations
from pathlib import Path
from typing import Dict, List
from fastapi import APIRouter

from modules.system_control.config_center.api._helpers import persist_modules_if_possible


def get_scan_router(modules: list, repo_root: Path, cfg_file_guess: Path) -> APIRouter:
    r = APIRouter(tags=["config_center-scan"])

    @r.post("/scan")
    def scan_and_register():
        base = repo_root / "modules"
        found: List[Dict[str, str]] = []
        for modcfg in sorted(base.glob("*/config/config.yml")):
            name = modcfg.parents[1].name
            rel = str(modcfg.relative_to(repo_root)).replace("\\", "/")
            found.append({"name": name, "path": rel})
        existing_names = {m.get("name") for m in modules}
        added: List[Dict[str, str]] = []
        for it in found:
            if it["name"] not in existing_names:
                modules.append(it)
                added.append(it)
        if added:
            persist_modules_if_possible(modules, cfg_file_guess)
        return {"ok": True, "added": added, "total": len(modules)}

    return r
