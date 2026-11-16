from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Query, Response


def get_runtime_router(runtime_registry: Any) -> APIRouter:
    r = APIRouter(tags=["config_center-runtime"])

    def _active_registry() -> Any:
        return runtime_registry() if callable(runtime_registry) else runtime_registry

    @r.get("/runtime/list")
    def runtime_list(module: Optional[str] = Query(default=None)):
        reg = _active_registry()
        if reg is None:
            return {"ok": False, "error": "runtime_registry_unavailable", "keys": []}
        return {"ok": True, "keys": reg.list_keys(module=module)}

    @r.get("/runtime/get")
    def runtime_get(key: str = Query(...)):
        reg = _active_registry()
        if reg is None:
            return Response(status_code=503, content="runtime registry unavailable")
        try:
            module, name = key.split(".", 1)
        except ValueError:
            return Response(status_code=400, content="invalid key")
        entry = reg.get(module, name)
        if entry is None:
            return Response(status_code=404, content="key not found")
        return entry

    @r.post("/runtime/set")
    def runtime_set(body: Dict[str, Any] = Body(...)):
        reg = _active_registry()
        if reg is None:
            return {"ok": False, "error": "runtime_registry_unavailable"}
        actor = str(body.get("actor", "admin"))
        source = str(body.get("source", "api"))
        items = body.get("items")
        if isinstance(items, dict):
            results = reg.bulk_set(items, actor=actor, source=source)
            return {"ok": all(res.get("ok") for res in results), "results": results}
        key = str(body.get("key", "")).strip()
        if not key:
            return {"ok": False, "error": "missing_key"}
        try:
            module, name = key.split(".", 1)
        except ValueError:
            return {"ok": False, "error": "invalid_key"}
        return reg.set(module, name, body.get("value"), actor=actor, source=source)

    @r.get("/runtime/audit")
    def runtime_audit(limit: int = Query(50, ge=1, le=500)):
        reg = _active_registry()
        if reg is None:
            return {"ok": False, "error": "runtime_registry_unavailable", "events": []}
        return {"ok": True, "events": reg.audit_log(limit=limit)}

    return r
