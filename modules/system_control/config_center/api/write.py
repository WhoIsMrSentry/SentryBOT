from __future__ import annotations
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Query, Response
import yaml

from modules.system_control.config_center.api._helpers import (
    atomic_write_text,
    backup_file,
    is_within_repo,
    list_backups,
    persist_modules_if_possible,
    resolve_module_config_path,
)


def get_write_router(
    modules: list,
    repo_root: Path,
    runtime_registry: Any,
    cfg_file_guess: Path,
    apply_module_yaml: Any,
    modules_lock: Optional[threading.RLock] = None,
) -> APIRouter:
    r = APIRouter(tags=["config_center-write"])

    def _active_registry() -> Any:
        return runtime_registry() if callable(runtime_registry) else runtime_registry

    def _run_apply(module: str, new_doc: Any, apply_runtime: bool) -> Dict[str, Any]:
        reg = _active_registry()
        if (
            apply_runtime
            and apply_module_yaml is not None
            and reg is not None
            and isinstance(new_doc, dict)
        ):
            return apply_module_yaml(reg, module, new_doc)
        if apply_runtime:
            return {"skipped": True, "reason": "no_registry_or_invalid_doc"}
        return {"skipped": True}

    @r.put("/set")
    def set_config(
        module: str,
        body: str = Body(..., media_type="text/plain"),
        apply_runtime: bool = Query(default=True),
        dry_run: bool = Query(default=False),
    ):
        p, err = resolve_module_config_path(modules, module, repo_root, lock=modules_lock)
        if err is not None:
            return err
        assert p is not None
        try:
            new_doc = yaml.safe_load(body)
        except Exception as e:
            return Response(status_code=400, content=f"yaml validation error: {e}")
        if new_doc is not None and not isinstance(new_doc, dict):
            return Response(
                status_code=400,
                content="yaml validation error: top-level document must be a mapping",
            )
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "valid": True,
                "keys": sorted(str(k) for k in new_doc.keys()) if isinstance(new_doc, dict) else [],
            }
        if p.exists():
            backup_file(p)
        atomic_write_text(p, body)
        runtime_payload = _run_apply(module, new_doc, apply_runtime)
        return {"ok": True, "runtime_apply": runtime_payload}

    @r.post("/rollback")
    def rollback_config(
        module: str,
        backup_name: Optional[str] = Query(default=None),
        apply_runtime: bool = Query(default=True),
    ):
        p, err = resolve_module_config_path(modules, module, repo_root, lock=modules_lock)
        if err is not None:
            return err
        assert p is not None
        backups = list_backups(p)
        if not backups:
            return Response(status_code=404, content="no backup found")

        if backup_name:
            target_backup = next((b for b in backups if b.name == backup_name), None)
            if target_backup is None:
                return Response(status_code=404, content="backup not found")
        else:
            target_backup = backups[0]

        try:
            backup_text = target_backup.read_text(encoding="utf-8")
            doc = yaml.safe_load(backup_text)
        except Exception as e:
            return Response(status_code=400, content=f"backup yaml validation error: {e}")

        if p.exists():
            backup_file(p)
        atomic_write_text(p, backup_text)
        runtime_payload = _run_apply(module, doc, apply_runtime)
        return {
            "ok": True,
            "module": module,
            "restored_from": target_backup.name,
            "runtime_apply": runtime_payload,
        }

    @r.post("/register")
    def register(name: str = Body(...), path: str = Body(...)):
        p = Path(path)
        if not p.is_absolute():
            p = (repo_root / path).resolve()
        else:
            p = p.resolve()
        if not p.exists() or not p.is_file():
            return Response(status_code=404, content="path not found")
        if not is_within_repo(p, repo_root):
            return Response(status_code=403, content="path outside workspace")
        entry = {"name": name, "path": str(p.relative_to(repo_root.resolve())).replace("\\", "/")}
        if modules_lock is not None:
            with modules_lock:
                idx = next((i for i, m in enumerate(modules) if m.get("name") == name), -1)
                if idx == -1:
                    modules.append(entry)
                else:
                    modules[idx] = entry
        else:
            idx = next((i for i, m in enumerate(modules) if m.get("name") == name), -1)
            if idx == -1:
                modules.append(entry)
            else:
                modules[idx] = entry
        persist_modules_if_possible(modules, cfg_file_guess, lock=modules_lock)
        return {"ok": True}

    return r
