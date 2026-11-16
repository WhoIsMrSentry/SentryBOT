from __future__ import annotations
import threading
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
    RuntimeConfigRegistry = None  # type: ignore[assignment,misc]

    def get_default_registry() -> Optional["RuntimeConfigRegistry"]:  # type: ignore[misc]
        return None

    apply_module_yaml = None  # type: ignore[assignment]

from modules.system_control.config_center.api.views import get_views_router
from modules.system_control.config_center.api.config_routes import get_config_router
from modules.system_control.config_center.api.write import get_write_router
from modules.system_control.config_center.api.runtime import get_runtime_router
from modules.system_control.config_center.api.scan import get_scan_router


def get_router(cfg: Dict[str, Any], registry: Optional["RuntimeConfigRegistry"] = None) -> APIRouter:
    modules: List[dict] = list(cfg.get("modules", []))
    modules_lock = threading.RLock()
    repo_root = Path(__file__).resolve().parents[4]
    cfg_file_guess = Path(__file__).resolve().parents[1] / "config" / "config.yml"
    static_dir = Path(__file__).resolve().parents[1] / "static"

    def _resolve_registry() -> Optional["RuntimeConfigRegistry"]:
        return registry if registry is not None else get_default_registry()

    r = APIRouter(prefix="/config", tags=["config_center"])

    if (static_dir / "index.html").is_file():
        r.include_router(get_views_router(static_dir))
    r.include_router(get_config_router(modules, repo_root, modules_lock=modules_lock))
    r.include_router(
        get_write_router(
            modules,
            repo_root,
            _resolve_registry,
            cfg_file_guess,
            apply_module_yaml,
            modules_lock=modules_lock,
        )
    )
    r.include_router(get_runtime_router(_resolve_registry))
    r.include_router(get_scan_router(modules, repo_root, cfg_file_guess, modules_lock=modules_lock))

    return r
