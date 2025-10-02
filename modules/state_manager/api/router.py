from __future__ import annotations
from typing import Dict, Any, List
from fastapi import APIRouter

from ..services.store import StateStore


def get_router(store: StateStore) -> APIRouter:
    r = APIRouter(prefix="/state", tags=["state"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/get")
    def get_state():
        return store.get()

    @r.post("/set/operational")
    def set_operational(body: Dict[str, Any]):
        store.set_operational(str(body.get("value", "idle")))
        return {"ok": True}

    @r.post("/set/emotions")
    def set_emotions(body: Dict[str, Any]):
        vals = body.get("values", [])
        if not isinstance(vals, list):
            vals = [str(vals)]
        store.set_emotions([str(v) for v in vals])
        return {"ok": True}

    return r
