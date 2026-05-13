from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
import shutil
import yaml

from fastapi import APIRouter, Body, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

try:
    from ..services.runtime_registry import (
        RuntimeConfigRegistry,
        get_default_registry,
    )
    from ..services.yaml_runtime_apply import apply_module_yaml
except Exception:  # pragma: no cover - allow degraded imports
    RuntimeConfigRegistry = None  # type: ignore
    get_default_registry = lambda: None  # type: ignore
    apply_module_yaml = None  # type: ignore


def _read_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_router(cfg: Dict[str, Any], registry: Optional["RuntimeConfigRegistry"] = None) -> APIRouter:
    """Config Center API router.

    Endpoints:
    - GET   /config/list       -> Known modules (name, path)
    - GET   /config/get        -> Parsed YAML content (JSON)
    - GET   /config/raw        -> Raw YAML content (download)
    - PUT   /config/set        -> Save YAML (validates, backups)
    - POST  /config/register   -> Register a module manually (kept for completeness)
    - POST  /config/scan       -> Auto-discover modules/*/config/config.yml and register missing
    - GET   /config/ui         -> Serve static UI index.html
    - MOUNT /config/static     -> Serve static assets (css/js)
    """

    r = APIRouter(prefix="/config", tags=["config_center"])

    modules: List[Dict[str, str]] = list(cfg.get("modules", []))
    runtime_registry = registry if registry is not None else get_default_registry()
    repo_root = Path(__file__).resolve().parents[3]
    cfg_file_guess = Path(__file__).resolve().parents[1] / "config" / "config.yml"

    def _is_within_repo(p: Path) -> bool:
        try:
            p.resolve().relative_to(repo_root)
            return True
        except Exception:
            return False

    def _backup_file(p: Path) -> None:
        try:
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            backup = p.with_suffix(p.suffix + f".bak-{ts}")
            shutil.copy2(p, backup)
        except Exception:
            # best-effort backup; ignore errors
            pass

    def _persist_modules_if_possible() -> None:
        """Persist current modules list into this module's config.yml, if present."""
        try:
            conf = {}
            if cfg_file_guess.exists():
                conf = yaml.safe_load(cfg_file_guess.read_text(encoding="utf-8")) or {}
            conf["modules"] = modules
            # backup and write
            if cfg_file_guess.exists():
                _backup_file(cfg_file_guess)
            cfg_file_guess.write_text(
                yaml.safe_dump(conf, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except Exception:
            # Do not crash API because of persistence issues
            pass

    # --- Static UI ---
    static_dir = Path(__file__).resolve().parents[1] / "static"

    @r.get("/ui", response_class=HTMLResponse)
    def ui():
        index_file = static_dir / "index.html"
        if not index_file.exists():
            return HTMLResponse("<h1>Config Center UI not found</h1>", status_code=404)
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    @r.get("/static/{file_path:path}")
    def serve_static(file_path: str):
        """Serve static assets for the Config Center UI under /config/static/*"""
        target = (static_dir / file_path).resolve()
        try:
            # prevent path traversal
            target.relative_to(static_dir.resolve())
        except Exception:
            return Response(status_code=403, content="invalid path")
        if not target.exists() or not target.is_file():
            return Response(status_code=404)
        return FileResponse(str(target))

    # --- Core endpoints ---
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
        # Normalize path relative to repo_root when needed
        p = Path(raw_path)
        if not p.is_absolute():
            p = (repo_root / raw_path).resolve()
        if not p.exists() or not p.is_file() or not _is_within_repo(p):
            return Response(status_code=404, content="file not found")
        try:
            data = _read_yaml(p)
        except Exception as e:
            return Response(status_code=400, content=f"yaml parse error: {e}")
        # FastAPI will serialize dict/list to JSON automatically
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
        if not p.exists() or not p.is_file() or not _is_within_repo(p):
            return Response(status_code=404, content="file not found")
        text = p.read_text(encoding="utf-8")
        return Response(
            content=text,
            media_type="text/yaml",
            headers={"Content-Disposition": f"attachment; filename={module}.yml"},
        )

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
        if not _is_within_repo(p):
            return Response(status_code=403, content="path outside workspace")
        try:
            new_doc = yaml.safe_load(body)
        except Exception as e:
            return Response(status_code=400, content=f"yaml validation error: {e}")
        if p.exists():
            _backup_file(p)
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
        if not _is_within_repo(p):
            return Response(status_code=403, content="path outside workspace")
        entry = {"name": name, "path": str(p.relative_to(repo_root)).replace("\\", "/")}
        # upsert by name
        idx = next((i for i, m in enumerate(modules) if m.get("name") == name), -1)
        if idx == -1:
            modules.append(entry)
        else:
            modules[idx] = entry
        _persist_modules_if_possible()
        return {"ok": True}

    # --- Runtime registry endpoints ---
    @r.get("/runtime/list")
    def runtime_list(module: Optional[str] = Query(default=None)):
        if runtime_registry is None:
            return {"ok": False, "error": "runtime_registry_unavailable", "keys": []}
        return {"ok": True, "keys": runtime_registry.list_keys(module=module)}

    @r.get("/runtime/get")
    def runtime_get(key: str = Query(...)):
        if runtime_registry is None:
            return Response(status_code=503, content="runtime registry unavailable")
        try:
            module, name = key.split(".", 1)
        except ValueError:
            return Response(status_code=400, content="invalid key")
        entry = runtime_registry.get(module, name)
        if entry is None:
            return Response(status_code=404, content="key not found")
        return entry

    @r.post("/runtime/set")
    def runtime_set(body: Dict[str, Any] = Body(...)):
        if runtime_registry is None:
            return {"ok": False, "error": "runtime_registry_unavailable"}
        actor = str(body.get("actor", "admin"))
        source = str(body.get("source", "api"))
        items = body.get("items")
        if isinstance(items, dict):
            results = runtime_registry.bulk_set(items, actor=actor, source=source)
            return {"ok": all(r.get("ok") for r in results), "results": results}
        key = str(body.get("key", "")).strip()
        if not key:
            return {"ok": False, "error": "missing_key"}
        try:
            module, name = key.split(".", 1)
        except ValueError:
            return {"ok": False, "error": "invalid_key"}
        return runtime_registry.set(module, name, body.get("value"), actor=actor, source=source)

    @r.get("/runtime/audit")
    def runtime_audit(limit: int = Query(50, ge=1, le=500)):
        if runtime_registry is None:
            return {"ok": False, "error": "runtime_registry_unavailable", "events": []}
        return {"ok": True, "events": runtime_registry.audit_log(limit=limit)}

    @r.post("/scan")
    def scan_and_register():
        """Scan modules/*/config/config.yml and register missing panels automatically."""
        base = repo_root / "modules"
        found: List[Dict[str, str]] = []
        for modcfg in sorted(base.glob("*/config/config.yml")):
            name = modcfg.parents[1].name  # modules/<name>/config/config.yml
            rel = str(modcfg.relative_to(repo_root)).replace("\\", "/")
            found.append({"name": name, "path": rel})
        existing_names = {m.get("name") for m in modules}
        added: List[Dict[str, str]] = []
        for it in found:
            if it["name"] not in existing_names:
                modules.append(it)
                added.append(it)
        if added:
            _persist_modules_if_possible()
        return {"ok": True, "added": added, "total": len(modules)}

    return r
