from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter

try:
    from ..services.runtime_registry import (
        RuntimeConfigRegistry,
        get_default_registry,
    )
    from ..services.yaml_runtime_apply import apply_module_yaml
except Exception:
    RuntimeConfigRegistry = None
    get_default_registry = lambda: None
    apply_module_yaml = None

from modules.system_control.config_center.api.views import get_views_router
from modules.system_control.config_center.api.config_routes import get_config_router
from modules.system_control.config_center.api.write import get_write_router
from modules.system_control.config_center.api.runtime import get_runtime_router
from modules.system_control.config_center.api.scan import get_scan_router


def get_router(cfg: Dict[str, Any], registry: Optional["RuntimeConfigRegistry"] = None) -> APIRouter:
    modules: List[dict] = list(cfg.get("modules", []))
    runtime_registry = registry if registry is not None else get_default_registry()
    repo_root = Path(__file__).resolve().parents[3]
    cfg_file_guess = Path(__file__).resolve().parents[1] / "config" / "config.yml"
    static_dir = Path(__file__).resolve().parents[1] / "static"

    r = APIRouter(prefix="/config", tags=["config_center"])

    r.include_router(get_views_router(static_dir))
    r.include_router(get_config_router(modules, repo_root))
    r.include_router(get_write_router(modules, repo_root, runtime_registry, cfg_file_guess, apply_module_yaml))
    r.include_router(get_runtime_router(runtime_registry))
    r.include_router(get_scan_router(modules, repo_root, cfg_file_guess))

    return r
