from __future__ import annotations

from fastapi import APIRouter

from modules.runtime_console.event_bus import get_event_bus

router = APIRouter(prefix="/runtime_console", tags=["runtime_console"])


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "events": len(list(get_event_bus().iter()))}


@router.get("/events")
def events(limit: int = 20) -> dict:
    return {"ok": True, "events": [event.__dict__ for event in get_event_bus().tail(limit)]}
