from __future__ import annotations

from fastapi import APIRouter
from typing import Any, Dict, Optional

try:
    from ..services.engine import InteractionEngine
except Exception:  # pragma: no cover
    from modules.interactions.services.engine import InteractionEngine  # type: ignore


def get_router(engine: InteractionEngine) -> APIRouter:
    r = APIRouter(prefix="/interactions")

    @r.get("/state")
    def state():
        return engine.get_state()

    @r.post("/event")
    def push_event(payload: Dict[str, Any]):
        t = str(payload.get("type", "")).strip()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else None
        if not t:
            return {"ok": False, "error": "type is required"}
        engine.push_event(t, data)
        return {"ok": True}

    @r.post("/effect")
    def effect(payload: Dict[str, Any]):
        name = str(payload.get("name", "COMET"))
        dur = int(payload.get("duration_ms", 800))
        engine.push_event("manual.effect", {"name": name, "duration_ms": dur})
        return {"ok": True}

    @r.post("/base")
    def base(payload: Dict[str, Any]):
        name = str(payload.get("name", "BREATHE"))
        color = payload.get("color")
        engine.set_state(manual_base=(name, color))
        return {"ok": True}

    return r
