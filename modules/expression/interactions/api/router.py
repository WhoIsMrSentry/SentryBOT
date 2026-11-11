from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from ..services.engine import InteractionEngine
except Exception:  # pragma: no cover
    from modules.expression.interactions.services.engine import InteractionEngine  # type: ignore


class EventRequest(BaseModel):
    type: str = ""
    data: Optional[Dict[str, Any]] = None


class EffectRequest(BaseModel):
    name: str = Field("COMET", min_length=1)
    duration_ms: int = Field(800, ge=0, le=60000)
    force: bool = False
    color: Optional[Union[str, List[int], Tuple[int, int, int]]] = None
    r: Optional[int] = Field(None, ge=0, le=255)
    g: Optional[int] = Field(None, ge=0, le=255)
    b: Optional[int] = Field(None, ge=0, le=255)
    emotions: Optional[List[str]] = None


class BaseRequest(BaseModel):
    name: str = Field("BREATHE", min_length=1)
    color: Optional[Union[str, List[int], Tuple[int, int, int]]] = None
    force: bool = False


def get_router(engine: InteractionEngine) -> APIRouter:
    r = APIRouter(prefix="/interactions", tags=["interactions"], responses={404: {"description": "Not found"}})

    @r.get("/state", tags=["interactions"], summary="State")
    def state():
        return engine.get_state()

    @r.get("/rules/trace", tags=["interactions"], summary="Rules Trace")
    def rules_trace():
        return engine.get_rules_trace()

    @r.post("/event", tags=["interactions"], summary="Push Event")
    def push_event(payload: EventRequest):
        t = str(payload.type or "").strip()
        if not t:
            return {"ok": False, "error": "type is required"}
        engine.push_event(t, payload.data)
        return {"ok": True}

    @r.post("/effect", tags=["interactions"], summary="Effect")
    def effect(payload: EffectRequest):
        color: Any = payload.color
        if color is None and payload.r is not None and payload.g is not None and payload.b is not None:
            color = (int(payload.r), int(payload.g), int(payload.b))
        return engine.request_effect(
            name=payload.name,
            duration_ms=payload.duration_ms,
            force=payload.force,
            color=color,
            emotions=payload.emotions,
        )

    @r.post("/base", tags=["interactions"], summary="Base")
    def base(payload: BaseRequest):
        return engine.request_base(name=payload.name, color=payload.color, force=payload.force)

    return r
