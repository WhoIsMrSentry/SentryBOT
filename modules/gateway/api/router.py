from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("gateway.router")

# Core gateway routes are intentionally read-only; no route bypasses e-stop or
# owner authorization because hardware commands are owned by module APIs.
ROUTE_MANIFEST = (
    {"path": "/healthz", "method": "GET", "auth": "none", "estop_required": False},
    {"path": "/readyz", "method": "GET", "auth": "none", "estop_required": False},
    {"path": "/status", "method": "GET", "auth": "none", "estop_required": False},
    {"path": "/health", "method": "GET", "auth": "none", "estop_required": False},
)

_INTERNAL_STARTED_KEYS = frozenset(
    {
        "gateway_base_url",
        "expression_arbiter",
        "head_arbiter",
        "camera_handle",
        "onsensor_bus",
        "imx500_runner",
        "device_manager",
        "wakeword_handle",
        "autonomy_started",
        "notifier_bot",
        "notifier_polling_enabled",
        "runtime_registry",
    }
)


def _probe_service(name: str, svc: object) -> Dict[str, Any]:
    if isinstance(svc, dict):
        info = dict(svc)
        info["ok"] = bool(info.get("ok", True))
        return info

    if isinstance(svc, bool):
        return {"ok": svc}

    for method_name in ("health", "status"):
        probe = getattr(svc, method_name, None)
        if callable(probe):
            try:
                res = probe()
                if isinstance(res, dict):
                    ok = bool(res.get("ok", True))
                    return {"ok": ok, "body": res} if method_name == "health" else {"ok": ok, "status": res}
                return {"ok": bool(res) if method_name == "health" else True, method_name: res}
            except Exception as exc:
                logger.debug("in-memory %s probe failed for %s: %s", method_name, name, exc)
                return {"ok": False, "error": str(exc)}

    for running_attr in ("is_running", "running"):
        probe = getattr(svc, running_attr, None)
        if callable(probe):
            try:
                return {"ok": True, "running": bool(probe())}
            except Exception as exc:
                logger.debug("in-memory running probe failed for %s: %s", name, exc)
                return {"ok": False, "error": str(exc)}

    return {"ok": True}


def _collect_module_health(started: Dict[str, object]) -> tuple[bool, Dict[str, Dict[str, Any]]]:
    modules: Dict[str, Dict[str, Any]] = {}
    all_ok = True
    for name, svc in list(started.items()):
        if str(name).startswith("_") or name in _INTERNAL_STARTED_KEYS:
            continue
        info = _probe_service(str(name), svc)
        modules[str(name)] = info
        if not info.get("ok", False):
            all_ok = False
    return all_ok, modules


def get_router(cfg: Dict[str, Any], started: Dict[str, object]) -> APIRouter:
    r = APIRouter()

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        startup = started.get("_startup_health", {"ok": True, "stage": "unknown"})
        startup_dict = dict(startup) if isinstance(startup, dict) else {"ok": False, "stage": "invalid"}
        modules_ok, modules = _collect_module_health(started)
        overall_ok = bool(startup_dict.get("ok", False)) and modules_ok
        return {"ok": overall_ok, "startup": startup_dict, "modules": modules}

    @r.get("/readyz")
    def readyz() -> JSONResponse:
        startup = started.get("_startup_health", {"ok": False, "stage": "starting"})
        startup_dict = dict(startup) if isinstance(startup, dict) else {"ok": False, "stage": "invalid"}
        manifest = started.get("_boot_manifest", [])
        boot_list = list(manifest) if isinstance(manifest, list) else []
        ready = bool(startup_dict.get("ok", False)) and startup_dict.get("stage") == "ready"
        slowest = max(
            boot_list,
            key=lambda item: float(item.get("duration_ms", 0.0)) if isinstance(item, dict) else 0.0,
            default=None,
        )
        payload = {
            "ok": ready,
            "ready": ready,
            "stage": startup_dict.get("stage", "unknown"),
            "total_boot_ms": started.get("_boot_total_ms", 0.0),
            "slowest_module": slowest,
            "boot_manifest": boot_list,
        }
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @r.get("/status")
    def status() -> Dict[str, Any]:
        include_cfg = dict(cfg.get("include", {}))
        started_names = [
            str(k)
            for k in started.keys()
            if not str(k).startswith("_") and k not in _INTERNAL_STARTED_KEYS
        ]
        configured_on = [k for k, v in include_cfg.items() if bool(v)]
        not_started = [k for k in configured_on if k not in started_names]
        return {
            "ok": True,
            "configured": include_cfg,
            "started": started_names,
            "not_started": not_started,
            "boot_total_ms": started.get("_boot_total_ms"),
        }

    @r.get("/health")
    def health() -> Dict[str, Any]:
        modules_ok, modules = _collect_module_health(started)
        startup = started.get("_startup_health", {"ok": True})
        startup_ok = bool(startup.get("ok", True)) if isinstance(startup, dict) else False
        return {"ok": startup_ok and modules_ok, **modules}

    return r
