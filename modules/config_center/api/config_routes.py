from __future__ import annotations
from pathlib import Path
from typing import List
from fastapi import APIRouter, Response

from modules.config_center.api._helpers import read_yaml, is_within_repo


def get_config_router(modules: List[dict], repo_root: Path) -> APIRouter:
    r = APIRouter(tags=["config_center-config"])

    @r.get("/list")
    def list_modules():
        return modules

    @r.get("/get")
    def get_config(module: str):
        item = next((m for m in modules if m.get("name") == module), None)
        if not item:
            return Response(status_code=404, content="module not found")
        raw_path = item.get("path")
        if not raw_path:
            return Response(status_code=404, content="path not set")
        p = Path(raw_path)
        if not p.is_absolute():
            p = (repo_root / raw_path).resolve()
        if not p.exists() or not p.is_file() or not is_within_repo(p, repo_root):
            return Response(status_code=404, content="file not found")
        try:
            data = read_yaml(p)
        except Exception as e:
            return Response(status_code=400, content=f"yaml parse error: {e}")
        return data

    @r.get("/raw")
    def get_config_raw(module: str):
        item = next((m for m in modules if m.get("name") == module), None)
        if not item:
            return Response(status_code=404, content="module not found")
        raw_path = item.get("path")
        if not raw_path:
            return Response(status_code=404, content="path not set")
        p = Path(raw_path)
        if not p.is_absolute():
            p = (repo_root / raw_path).resolve()
        if not p.exists() or not p.is_file() or not is_within_repo(p, repo_root):
            return Response(status_code=404, content="file not found")
        text = p.read_text(encoding="utf-8")
        return Response(
            content=text,
            media_type="text/yaml",
            headers={"Content-Disposition": f"attachment; filename={module}.yml"},
        )

    return r
