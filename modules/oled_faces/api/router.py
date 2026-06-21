from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter


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
    def manual(payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(payload.get("mode", "bitmap"))
        name = str(payload.get("name", "normal"))
        return service.apply_manual(mode=mode, name=name)

    @r.post("/event")
    def push_event(payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = str(payload.get("type", ""))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if not event_type:
            return {"ok": False, "error": "type is required"}
        service.on_interaction_event(event_type, data)
        return {"ok": True}

    return r
