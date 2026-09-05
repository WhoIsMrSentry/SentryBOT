from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Query, Response
import yaml

from modules.system_control.config_center.api._helpers import is_within_repo, backup_file, persist_modules_if_possible


def get_write_router(
    modules: list,
    repo_root: Path,
    runtime_registry: Any,
    cfg_file_guess: Path,
    apply_module_yaml: Any,
) -> APIRouter:
    r = APIRouter(tags=["config_center-write"])

    @r.put("/set")
    def set_config(
        module: str,
        body: str = Body(..., media_type="text/plain"),
        apply_runtime: bool = Query(default=True),
    ):
        item = next((m for m in modules if m.get("name") == module), None)
        if not item:
            return Response(status_code=404, content="module not found")
        raw_path = item.get("path")
        if not raw_path:
            return Response(status_code=404, content="path not set")
        p = Path(raw_path)
        if not p.is_absolute():
            p = (repo_root / raw_path).resolve()
        if not is_within_repo(p, repo_root):
            return Response(status_code=403, content="path outside workspace")
        try:
            new_doc = yaml.safe_load(body)
        except Exception as e:
            return Response(status_code=400, content=f"yaml validation error: {e}")
        if p.exists():
            backup_file(p)
        p.write_text(body, encoding="utf-8")
        runtime_payload: Dict[str, Any] = {"skipped": True}
        if (
            apply_runtime
            and apply_module_yaml is not None
            and runtime_registry is not None
            and isinstance(new_doc, dict)
        ):
            runtime_payload = apply_module_yaml(runtime_registry, module, new_doc)
        elif apply_runtime:
            runtime_payload = {"skipped": True, "reason": "no_registry_or_invalid_doc"}
        return {"ok": True, "runtime_apply": runtime_payload}

    @r.post("/register")
    def register(name: str = Body(...), path: str = Body(...)):
        p = Path(path)
        if not p.is_absolute():
            p = (repo_root / path).resolve()
        if not p.exists() or not p.is_file():
            return Response(status_code=404, content="path not found")
        if not is_within_repo(p, repo_root):
            return Response(status_code=403, content="path outside workspace")
        entry = {"name": name, "path": str(p.relative_to(repo_root)).replace("\\", "/")}
        idx = next((i for i, m in enumerate(modules) if m.get("name") == name), -1)
        if idx == -1:
            modules.append(entry)
        else:
            modules[idx] = entry
        persist_modules_if_possible(modules, cfg_file_guess)
        return {"ok": True}

    return r
