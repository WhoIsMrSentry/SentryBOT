from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Query, Response


def get_runtime_router(runtime_registry: Any) -> APIRouter:
    r = APIRouter(tags=["config_center-runtime"])

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

    return r
