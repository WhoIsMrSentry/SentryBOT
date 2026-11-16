from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator


class ManualRequest(BaseModel):
    mode: Literal["bitmap", "animation", "logo", "gesture", "vibe", "test"] = "bitmap"
    name: str = Field(default="normal", min_length=1, max_length=64)
    duration_s: Optional[float] = Field(default=None, gt=0.0, le=300.0)
    loop: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("name must not be empty")
        return s


class EventRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=128)
    data: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _strip_type(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("type must not be empty")
        return s


class SttTextRequest(BaseModel):
    text: str = Field(default="", max_length=512)
    duration_s: float = Field(default=4.5, gt=0.0, le=60.0)


def get_router(service: Any) -> APIRouter:
    r = APIRouter(prefix="/oled_faces", tags=["oled_faces"])

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        st = service.status()
        return {**st, "ok": bool(st.get("has_display"))}

    @r.get("/status")
    def status() -> Dict[str, Any]:
        return service.status()

    @r.get("/catalog")
    def catalog() -> Dict[str, Any]:
        from ..services.catalog_registry import (
            MOTOR_ACTIVITIES,
            MOTOR_GESTURES,
            MOTOR_MOODS,
            build_motor_event_map,
        )
        events = build_motor_event_map()
        return {
            "moods": list(MOTOR_MOODS),
            "gestures": list(MOTOR_GESTURES),
            "activities": list(MOTOR_ACTIVITIES),
            "events": events,
            "trigger_examples": {
                "mood": "POST /oled_faces/event {\"type\": \"emotion:chill\"}",
                "gesture": "POST /oled_faces/event {\"type\": \"gesture:nod\"}",
                "activity": "POST /oled_faces/event {\"type\": \"activity:debugging\"}",
                "manual": "POST /oled_faces/manual {\"mode\": \"animation\", \"name\": \"deploying\"}",
            },
        }

    @r.post("/manual")
    def manual(payload: ManualRequest) -> Dict[str, Any]:
        return service.apply_manual(mode=payload.mode, name=payload.name)

    @r.post("/event")
    def push_event(payload: EventRequest) -> Dict[str, Any]:
        service.on_interaction_event(payload.type, payload.data)
        return {"ok": True}

    @r.post("/stt_text")
    def post_stt_text(payload: SttTextRequest) -> Any:
        text = payload.text.strip()
        eng = getattr(getattr(service, "display", None), "_engine", None)
        if eng is not None:
            eng.set_stt_text(text, duration_s=payload.duration_s)
            drv = getattr(getattr(service, "display", None), "_driver", None)
            if text and drv is not None and hasattr(drv, "notify_activity"):
                drv.notify_activity()
            return {"ok": True, "text": text, "cleared": not bool(text)}
        return JSONResponse(status_code=503, content={"ok": False, "error": "engine not started"})

    return r
