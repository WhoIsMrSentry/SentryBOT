from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter


def get_router(service: Any) -> APIRouter:
    r = APIRouter(prefix="/oled_faces", tags=["oled_faces"])

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        st = service.status()
        return {"ok": bool(st.get("has_arduino")), **st}

    @r.get("/status")
    def status() -> Dict[str, Any]:
        return service.status()

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
