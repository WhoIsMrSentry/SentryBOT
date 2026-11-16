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
        laya = getattr(agent, "laya_engine", None)
        s1_summary: Dict[str, Any] = {"available": laya is not None}
        if laya is not None and hasattr(laya, "get_telemetry"):
            try:
                tel = laya.get_telemetry() or {}
                s1_summary = {
                    "available": True,
                    "backend": tel.get("cascade_backend") or ("laya" if hasattr(laya, "decide") else "none"),
                    "last_backend": tel.get("last_backend", ""),
                    "tier_counts": tel.get("tier_counts", {}),
                    "cache": tel.get("cache", {}),
                }
            except Exception:
                s1_summary = {"available": True}
        pm = getattr(agent, "progress_manager", None)
        arbiters_summary: Dict[str, Any] = {}
        if pm is not None and hasattr(pm, "arbiter_snapshot"):
            try:
                arbiters_summary = pm.arbiter_snapshot()
            except Exception:
                arbiters_summary = {}
        registry = getattr(agent, "tool_registry", None)
        tool_metrics = registry.metrics() if registry is not None and hasattr(registry, "metrics") else {}
        return {
            "ok": True,
            "state": "BUSY" if agent.is_busy else "IDLE",
            "system1": s1_summary,
            "arbiters": arbiters_summary,
            "tool_metrics": tool_metrics,
        }

    @router.get("/latency/latest")
    def latest_latency() -> Dict[str, Any]:
        trace = latency_trace.latest()
        return {"ok": trace is not None, "trace": trace}

    @router.get("/latency/{trace_id}")
    def latency(trace_id: str) -> Dict[str, Any]:
        trace = latency_trace.get(trace_id)
        return {"ok": trace is not None, "trace": trace}

    @router.get("/decision-traces")
    def decision_traces(
        limit: int = 20,
        goal_id: Optional[str] = None,
        since: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Safe decision summaries (no chain-of-thought / prompts / secrets)."""
        store = getattr(agent, "decision_traces", None)
        if store is None or not hasattr(store, "query"):
            return {"ok": False, "available": False, "traces": [], "reason": "decision_traces_unavailable"}
        capped = max(1, min(int(limit or 20), 100))
        traces = store.query(limit=capped, goal_id=goal_id, since=since)
        return {
            "ok": True,
            "available": True,
            "count": len(traces),
            "maxlen": int(getattr(store, "maxlen", 0) or 0),
            "traces": traces,
        }

    @router.get("/decision-traces/latest")
    def decision_traces_latest(limit: int = 5) -> Dict[str, Any]:
        store = getattr(agent, "decision_traces", None)
        if store is None or not hasattr(store, "query"):
            return {"ok": False, "available": False, "traces": [], "reason": "decision_traces_unavailable"}
        capped = max(1, min(int(limit or 5), 20))
        traces = store.query(limit=capped)
        return {"ok": True, "available": True, "count": len(traces), "traces": traces}

    @router.get("/goals/status")
    def goals_status() -> Dict[str, Any]:
        """Read-only active/waiting GoalStore snapshot + latest replan reason."""
        store = getattr(agent, "goal_store", None)
        trace_store = getattr(agent, "decision_traces", None)
        latest_replan = (
            trace_store.latest_replan()
            if trace_store is not None and hasattr(trace_store, "latest_replan")
            else None
        )
        if store is None or not hasattr(store, "status_summary"):
            return {
                "ok": True,
                "available": False,
                "goals": [],
                "counts": {"active": 0, "waiting": 0, "replanning": 0, "terminal": 0},
                "latest_replan": latest_replan,
            }
        return {
            "ok": True,
            "available": True,
            **store.status_summary(),
            "latest_replan": latest_replan,
        }

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
        use_native = (
            bool(getattr(agent, "api_native_tools", False))
            and not bool(getattr(agent, "tri_layer_enabled", False))
            if native_tools is None
            else bool(native_tools)
        )
        trace_id = str(trace_id or uuid.uuid4().hex[:16])
        result = agent.step(
            query,
            native_tools=use_native,
            trace_id=trace_id,
            language=language,
            speaker=speaker,
        )
        return result or {"text": "", "thoughts": "idle", "actions": [], "trace_id": trace_id}

    @router.post("/step_event")
    def step_event(
        event_type: str = Body(embed=True),
        event_prompt: str = Body(embed=True),
        language: Optional[str] = Body(default=None, embed=True),
        speaker: Optional[str] = Body(default=None, embed=True),
        trace_id: Optional[str] = Body(default=None, embed=True),
    ) -> Dict[str, Any]:
        """Event-driven step that bypasses cooldown and empty-prompt checks.

        Used by autonomy brain for spontaneous reactions (sound, vision, boredom).
        """
        if not hasattr(agent, "step_event"):
            return {"ok": False, "error": "step_event not available"}
        trace_id = str(trace_id or uuid.uuid4().hex[:16])
        result = agent.step_event(
            event_type=event_type,
            event_prompt=event_prompt,
            language=language,
            speaker=speaker,
            trace_id=trace_id,
        )
        return result or {"text": "", "thoughts": f"{event_type} handled", "actions": [], "trace_id": trace_id}

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
        use_native = (
            bool(getattr(agent, "api_native_tools", False))
            and not bool(getattr(agent, "tri_layer_enabled", False))
            if native_tools is None
            else bool(native_tools)
        )
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
