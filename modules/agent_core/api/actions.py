from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import json
import time


def get_actions_router(agent) -> APIRouter:
    router = APIRouter(tags=["agent-actions"])

    @router.get("/actions/status")
    def actions_status():
        if not hasattr(agent, 'action_arbiter') or agent.action_arbiter is None:
            return {"ok": False, "error": "action arbiter not available"}
        status = agent.action_arbiter.get_exclusive_status()
        return {
            "ok": True,
            "exclusive_locks": status,
            "vision_arbiter": agent.vision_arbiter.status() if hasattr(agent, "vision_arbiter") else {},
            "expression_arbiter": agent.expression_arbiter.status() if hasattr(agent, "expression_arbiter") else {},
            "speech": agent.speech_arbiter.get_status() if hasattr(agent, "speech_arbiter") else {},
        }

    @router.get("/arbiters/status")
    def arbiters_status():
        pm = getattr(agent, "progress_manager", None)
        if pm is None or not hasattr(pm, "arbiter_snapshot"):
            return {"ok": False, "error": "progress_manager unavailable"}
        snapshot = pm.arbiter_snapshot()
        return {"ok": True, **snapshot}

    @router.get("/arbiters/stream")
    def arbiters_stream(interval_s: float = Query(1.0, ge=0.2, le=10.0)):
        pm = getattr(agent, "progress_manager", None)
        if pm is None or not hasattr(pm, "arbiter_snapshot"):
            return {"ok": False, "error": "progress_manager unavailable"}

        def gen():
            yield f"data: {json.dumps({'type': 'arbiter_status', 'snapshot': pm.arbiter_snapshot()}, default=str)}\n\n"
            while True:
                time.sleep(max(0.2, float(interval_s)))
                try:
                    payload = {"type": "arbiter_status", "snapshot": pm.arbiter_snapshot()}
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
                except GeneratorExit:
                    break
                except Exception as exc:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                    break

        return StreamingResponse(gen(), media_type="text/event-stream")

    @router.post("/actions/queue")
    def actions_queue(body: dict = Body(...)):
        if not hasattr(agent, 'action_arbiter') or agent.action_arbiter is None:
            return {"ok": False, "error": "action arbiter not available"}

        from ..services.action_arbiter import ActionRequest

        action_type = str(body.get("type", "")).strip()
        priority = int(body.get("priority", 50))
        ttl_ms = int(body.get("ttl_ms", 5000))
        payload = body.get("payload", {})
        source = str(body.get("source", "agent_core")).strip()

        req = ActionRequest(
            type=action_type,
            source=source,
            priority=priority,
            ttl_ms=ttl_ms,
            payload=payload,
        )
        result = agent.action_arbiter.submit(req)
        return result

    @router.post("/actions/cancel")
    def actions_cancel(action_id: str = Body(embed=True)):
        if not hasattr(agent, 'action_arbiter') or agent.action_arbiter is None:
            return {"ok": False, "error": "action arbiter not available"}
        cancelled = agent.action_arbiter.cancel(action_id)
        return {"ok": cancelled, "action_id": action_id}

    @router.post("/progress")
    def progress_push(body: dict = Body(...)):
        if not hasattr(agent, 'progress_manager') or agent.progress_manager is None:
            return {"ok": False, "error": "progress manager not available"}
        try:
            agent.progress_manager.on_progress_event(dict(body))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @router.post("/events")
    def events_push(body: dict = Body(...)):
        if not hasattr(agent, "action_arbiter") or agent.action_arbiter is None:
            return {"ok": False, "error": "action arbiter not available"}
        from ..services.action_arbiter import ActionRequest, ActionPriority
        event_type = str(body.get("type", "")).strip().lower()
        payload = body.get("payload", {}) if isinstance(body.get("payload", {}), dict) else {}
        pri_map = {
            "hazard_detected": int(ActionPriority.SAFETY),
            "owner_follow_intent": int(ActionPriority.OWNER_FOLLOW),
            "new_person_seen": int(ActionPriority.VLM_INTEREST),
            "idle_comment_request": int(ActionPriority.AUTONOMY_IDLE),
        }
        source_map = {
            "hazard_detected": "safety",
            "owner_follow_intent": "owner_follow",
            "new_person_seen": "vlm_bridge",
            "idle_comment_request": "autonomy",
        }
        req = ActionRequest(
            type="notification",
            source=source_map.get(event_type, "autonomy"),
            priority=pri_map.get(event_type, int(ActionPriority.AUTONOMY_IDLE)),
            ttl_ms=2000,
            cooldown_key=f"event:{event_type}",
            payload={"event_type": event_type, **payload},
        )
        result = agent.action_arbiter.submit(req)
        return {"ok": True, "result": result}

    @router.get("/progress/latest")
    def progress_latest():
        if not hasattr(agent, 'progress_manager') or agent.progress_manager is None:
            return {"available": False, "progress": None}
        latest = agent.progress_manager.get_latest_event() if hasattr(agent.progress_manager, "get_latest_event") else {}
        if not latest:
            return {"available": False, "progress": None}
        return {"available": True, "progress": latest}

    return router
