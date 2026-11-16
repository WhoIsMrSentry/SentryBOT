from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..services.store import StateStore

_ALLOWED_OPERATIONAL_STATES = frozenset({
    "idle",
    "active",
    "busy",
    "listening",
    "speaking",
    "thinking",
    "sleep",
    "sleeping",
    "degraded",
    "failed",
    "maintenance",
    "estop",
    "error",
})


def get_router(store: StateStore) -> APIRouter:
    r = APIRouter(prefix="/state", tags=["state"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/get")
    def get_state(key: Optional[str] = Query(default=None)):
        if key is not None:
            if not store.has_key(key):
                raise HTTPException(status_code=404, detail=f"unknown state key: {key}")
            return {key: store.get(key=key)}
        return store.get()

    @r.post("/set")
    def set_state(body: Dict[str, Any]):
        if not isinstance(body, dict):
            return {"ok": False, "error": "body must be an object"}
        store.update(body)
        return {"ok": True}

    @r.post("/set/operational")
    def set_operational(body: Dict[str, Any]):
        val = str(body.get("value", "idle")).strip()
        if val not in _ALLOWED_OPERATIONAL_STATES:
            raise HTTPException(
                status_code=400,
                detail=f"invalid operational state {val!r}; allowed={sorted(_ALLOWED_OPERATIONAL_STATES)}",
            )
        store.set_operational(val)
        return {"ok": True, "operational": val}

    @r.post("/set/emotions")
    def set_emotions(body: Dict[str, Any]):
        vals = body.get("values", [])
        if not isinstance(vals, list):
            vals = [str(vals)]
        store.set_emotions([str(v) for v in vals])
        return {"ok": True}

    @r.get("/stream")
    async def stream_state(
        request: Request,
        max_events: Optional[int] = Query(default=None, ge=1, le=1000),
        heartbeat_s: float = Query(default=15.0, ge=0.05, le=60.0),
    ):
        """Stream state updates via Server-Sent Events (SSE)."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=64)

        def _on_change(key: str, value: Any) -> None:
            payload = {"key": key, "value": value}

            def _enqueue() -> None:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

            try:
                loop.call_soon_threadsafe(_enqueue)
            except RuntimeError:
                pass

        store.subscribe(_on_change)

        async def _events():
            sent = 0
            try:
                initial = json.dumps(store.get(), ensure_ascii=True, default=str)
                yield f"event: snapshot\ndata: {initial}\n\n"
                sent += 1
                if max_events is not None and sent >= max_events:
                    return

                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
                        body = json.dumps(item, ensure_ascii=True, default=str)
                        yield f"event: state\ndata: {body}\n\n"
                        sent += 1
                        if max_events is not None and sent >= max_events:
                            break
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                store.unsubscribe(_on_change)

        return StreamingResponse(_events(), media_type="text/event-stream")

    return r
