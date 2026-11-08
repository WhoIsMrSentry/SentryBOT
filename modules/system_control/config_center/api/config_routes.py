from __future__ import annotations
import threading
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Response

from modules.system_control.config_center.api._helpers import read_yaml, resolve_module_config_path


def get_config_router(
    modules: List[dict],
    repo_root: Path,
    modules_lock: Optional[threading.RLock] = None,
) -> APIRouter:
    r = APIRouter(tags=["config_center-config"])

    @r.get("/list")
    def list_modules():
        if modules_lock is not None:
            with modules_lock:
                return list(modules)
        return list(modules)

    @r.get("/get")
    def get_config(module: str):
        p, err = resolve_module_config_path(modules, module, repo_root, lock=modules_lock)
        if err is not None:
            return err
        assert p is not None
        if not p.exists() or not p.is_file():
            return Response(status_code=404, content="file not found")
        try:
            data = read_yaml(p)
        except Exception as e:
            return Response(status_code=400, content=f"yaml parse error: {e}")
        return data

    @r.get("/raw")
    def get_config_raw(module: str):
        p, err = resolve_module_config_path(modules, module, repo_root, lock=modules_lock)
        if err is not None:
            return err
        assert p is not None
        if not p.exists() or not p.is_file():
            return Response(status_code=404, content="file not found")
        text = p.read_text(encoding="utf-8")
        return Response(
            content=text,
            media_type="text/yaml",
            headers={"Content-Disposition": f"attachment; filename={module}.yml"},
        )

    return r
