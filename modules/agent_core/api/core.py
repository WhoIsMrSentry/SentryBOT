from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from modules.common.latency_trace import latency_trace


def get_core_router(agent) -> APIRouter:
    router = APIRouter(tags=["agent-core"])

    @router.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {"ok": True, "state": "BUSY" if agent.is_busy else "IDLE"}

    @router.get("/latency/latest")
    def latest_latency() -> Dict[str, Any]:
        trace = latency_trace.latest()
        return {"ok": trace is not None, "trace": trace}

    @router.get("/latency/{trace_id}")
    def latency(trace_id: str) -> Dict[str, Any]:
        trace = latency_trace.get(trace_id)
        return {"ok": trace is not None, "trace": trace}

    @router.post("/speech/interrupt")
    def speech_interrupt() -> Dict[str, Any]:
        return {"ok": True, "cleared": agent.speech_arbiter.interrupt_all()}

    @router.post("/step")
    def step(
        query: str = Body(embed=True),
        native_tools: Optional[bool] = Body(default=None, embed=True),
        trace_id: Optional[str] = Body(default=None, embed=True),
        language: Optional[str] = Body(default=None, embed=True),
        speaker: Optional[str] = Body(default=None, embed=True),
    ) -> Dict[str, Any]:
        use_native = bool(getattr(agent, "api_native_tools", False)) if native_tools is None else bool(native_tools)
        trace_id = str(trace_id or uuid.uuid4().hex[:16])
        result = agent.step(
            query,
            native_tools=use_native,
            trace_id=trace_id,
            language=language,
            speaker=speaker,
        )
        return result or {"text": "", "thoughts": "idle", "actions": [], "trace_id": trace_id}

    @router.post("/step_stream")
    def step_stream(
        query: str = Body(embed=True),
        native_tools: Optional[bool] = Body(default=None, embed=True),
        trace_id: Optional[str] = Body(default=None, embed=True),
        language: Optional[str] = Body(default=None, embed=True),
        speaker: Optional[str] = Body(default=None, embed=True),
    ) -> StreamingResponse:
        event_q: queue.Queue[Dict[str, Any]] = queue.Queue()
        done = threading.Event()
        result_holder: Dict[str, Any] = {}
        use_native = bool(getattr(agent, "api_native_tools", False)) if native_tools is None else bool(native_tools)
        trace_id = str(trace_id or uuid.uuid4().hex[:16])

        def emit(event: Dict[str, Any]) -> None:
            event_q.put({**event, "trace_id": trace_id})

        def worker() -> None:
            try:
                result_holder["result"] = agent.step(
                    query,
                    progress_cb=emit,
                    native_tools=use_native,
                    trace_id=trace_id,
                    language=language,
                    speaker=speaker,
                ) or {"text": "", "thoughts": "idle", "actions": [], "trace_id": trace_id}
            except Exception as exc:
                result_holder["error"] = str(exc)
                latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            finally:
                done.set()
                event_q.put({"type": "_done"})

        threading.Thread(target=worker, daemon=True).start()
        cfg_agent = agent.config.get("agent", {}) if isinstance(getattr(agent, "config", {}), dict) else {}
        waiting_messages = [str(item) for item in cfg_agent.get("waiting_messages", []) if str(item).strip()]
        heartbeat_s = float(getattr(agent, "status_interval_s", 2.0))

        def serialize(payload: Dict[str, Any]) -> str:
            return json.dumps(payload, ensure_ascii=True, default=str)

        def generate():
            last_beat = 0.0
            wait_index = 0
            yield f"data: {serialize({'type': 'status', 'trace_id': trace_id, 'text': 'Istek alindi.'})}\n\n"
            while not done.is_set() or not event_q.empty():
                try:
                    event = event_q.get(timeout=0.2)
                    if event.get("type") == "_done":
                        break
                    yield f"data: {serialize(event)}\n\n"
                except queue.Empty:
                    now = time.time()
                    if waiting_messages and now - last_beat >= heartbeat_s:
                        last_beat = now
                        text = waiting_messages[wait_index % len(waiting_messages)]
                        wait_index += 1
                        yield f"data: {serialize({'type': 'waiting', 'trace_id': trace_id, 'text': text})}\n\n"
            if "error" in result_holder:
                yield f"data: {serialize({'type': 'error', 'trace_id': trace_id, 'text': result_holder['error']})}\n\n"
            else:
                yield f"data: {serialize({'type': 'final', 'trace_id': trace_id, 'result': result_holder.get('result')})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.post("/route_preview")
    def route_preview(query: str = Body(embed=True)) -> Dict[str, Any]:
        return agent.route_preview(query)

    return router
