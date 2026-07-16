from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Query

from ..services.output_bridge import ExpressionOutputBridge
from ..services.state import SemanticExpressionEngine


def get_router(engine: SemanticExpressionEngine) -> APIRouter:
    router = APIRouter(prefix="/expression", tags=["expression"])
    bridge = ExpressionOutputBridge(engine)

    @router.get("/state")
    def state() -> Dict[str, Any]:
        return engine.get_state()

    @router.get("/status")
    def status() -> Dict[str, Any]:
        return {"ok": True, "engine": engine.status(), "output": bridge.status()}

    @router.get("/history")
    def history(limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
        return engine.history(limit=limit)

    @router.post("/state")
    def set_state(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        semantic = engine.apply(payload, source="api", reason=str(payload.get("reason") or "manual"))
        return {"ok": True, "semantic": semantic, "output": bridge.apply()}

    @router.post("/event")
    def event(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        event_type = str(payload.get("type") or payload.get("event") or "").strip()
        if not event_type:
            return {"ok": False, "error": "type is required"}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        semantic = engine.event(event_type, data)
        return {"ok": True, "semantic": semantic, "output": bridge.apply()}

    @router.get("/output/status")
    def output_status() -> Dict[str, Any]:
        return bridge.status()

    @router.get("/output/plan")
    def output_plan() -> Dict[str, Any]:
        return bridge.plan()

    @router.post("/output/apply")
    def output_apply() -> Dict[str, Any]:
        return bridge.apply()

    return router
