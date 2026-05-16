from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional
import json
import queue
import threading
import time


def get_router(agent) -> APIRouter:
    router = APIRouter(tags=["Agent Core"])

    @router.get("/healthz")
    def healthz():
        state_str = "BUSY" if agent.is_busy else "IDLE"
        return {"ok": True, "state": state_str}

    @router.post("/step")
    def step(query: str = Body(embed=True)):
        """Tek bir agent adımı çalıştır (ReAct + Tool Calling + Safety)."""
        result = agent.step(query)
        return result or {"text": "", "thoughts": "idle", "actions": []}

    @router.post("/step_stream")
    def step_stream(query: str = Body(embed=True)):
        """Stream agent progress as Server-Sent Events (SSE)."""
        event_q: queue.Queue[Dict[str, Any]] = queue.Queue()
        done = threading.Event()
        result_holder: Dict[str, Any] = {}

        def emit(event: Dict[str, Any]) -> None:
            event_q.put(event)

        def worker() -> None:
            try:
                res = agent.step(query, progress_cb=emit)
                result_holder["result"] = res or {"text": "", "thoughts": "idle", "actions": []}
            except Exception as exc:
                result_holder["error"] = str(exc)
            finally:
                done.set()
                event_q.put({"type": "_done"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        waiting_messages = [
            "Beklemedeyim...",
            "Islem suruyor...",
            "Hala isliyorum...",
        ]
        cfg_agent = agent.config.get("agent", {}) if isinstance(getattr(agent, "config", {}), dict) else {}
        cfg_waiting = cfg_agent.get("waiting_messages")
        if isinstance(cfg_waiting, list) and cfg_waiting:
            waiting_messages = [str(m) for m in cfg_waiting if str(m).strip()]
        heartbeat_s = float(getattr(agent, "status_interval_s", 2.0))

        def _serialize(payload: Dict[str, Any]) -> str:
            return json.dumps(payload, ensure_ascii=True, default=str)

        def gen():
            last_beat = 0.0
            wait_idx = 0
            # send immediate ack
            yield f"data: {_serialize({'type': 'status', 'text': 'Istek alindi, islem basladi.'})}\n\n"
            while not done.is_set() or not event_q.empty():
                try:
                    event = event_q.get(timeout=0.2)
                    if event.get("type") == "_done":
                        break
                    yield f"data: {_serialize(event)}\n\n"
                except queue.Empty:
                    now = time.time()
                    if now - last_beat >= heartbeat_s:
                        last_beat = now
                        if waiting_messages:
                            msg = waiting_messages[wait_idx % len(waiting_messages)]
                            wait_idx += 1
                            yield f"data: {_serialize({'type': 'waiting', 'text': msg})}\n\n"

            if "error" in result_holder:
                yield f"data: {_serialize({'type': 'error', 'text': result_holder['error']})}\n\n"
            else:
                yield f"data: {_serialize({'type': 'final', 'result': result_holder.get('result')})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @router.post("/route_preview")
    def route_preview(query: str = Body(embed=True)):
        """Tri-layer router'in hangi sub-agentlari sececegini onizle."""
        return agent.route_preview(query)

    @router.get("/world_state")
    def world_state():
        """Anlık dünya durumunu döndür."""
        return agent.world_state.get_state()

    @router.get("/memory/search")
    def search_memory(query: str, limit: int = 5):
        """Epizodik hafızada arama yap."""
        return {"results": agent.memory.search_memory(query, limit)}

    @router.get("/slam/location")
    def get_location():
        """Robotun topolojik haritadaki konumunu döndür."""
        return {"location": agent.slam.get_location()}

    @router.get("/slam/pathfind")
    def pathfind(destination: str):
        """Hedef odaya yol bul (BFS)."""
        path = agent.slam.pathfind(destination)
        return {"destination": destination, "path": path}

    # -----------------------------------------------------------------
    # Living Vision Agent: Action and Progress endpoints
    # -----------------------------------------------------------------

    @router.get("/actions/status")
    def actions_status():
        """Get current action arbiter status and exclusive locks."""
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

    @router.post("/actions/queue")
    def actions_queue(body: dict = Body(...)):
        """Submit an action to the action arbiter."""
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
        """Cancel a specific action by ID."""
        if not hasattr(agent, 'action_arbiter') or agent.action_arbiter is None:
            return {"ok": False, "error": "action arbiter not available"}
        cancelled = agent.action_arbiter.cancel(action_id)
        return {"ok": cancelled, "action_id": action_id}

    @router.post("/progress")
    def progress_push(body: dict = Body(...)):
        """Push external progress event into progress manager."""
        if not hasattr(agent, 'progress_manager') or agent.progress_manager is None:
            return {"ok": False, "error": "progress manager not available"}
        try:
            agent.progress_manager.on_progress_event(dict(body))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @router.post("/events")
    def events_push(body: dict = Body(...)):
        """Receive autonomy/vision events and queue prioritized actions."""
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
        """Get the latest progress event cache (if available)."""
        if not hasattr(agent, 'progress_manager') or agent.progress_manager is None:
            return {"available": False, "progress": None}
        latest = agent.progress_manager.get_latest_event() if hasattr(agent.progress_manager, "get_latest_event") else {}
        if not latest:
            return {"available": False, "progress": None}
        return {
            "available": True,
            "progress": latest,
        }

    # -----------------------------------------------------------------
    # Realtime Performance Profile Switch
    # -----------------------------------------------------------------

    @router.get("/profile")
    def get_profile():
        """Return active realtime profile and available modes."""
        rt_cfg = agent.config.get("realtime_profile", {})
        active = str(rt_cfg.get("active", "fast"))
        return {
            "ok": True,
            "active": active,
            "modes": ["fast", "normal"],
            "settings": rt_cfg.get(active, {}),
        }

    @router.post("/profile/switch")
    def switch_profile(
        mode: Optional[str] = Body(default=None, embed=True),
        mode_q: Optional[str] = Query(default=None, alias="mode"),
    ):
        """Switch realtime profile: 'fast' or 'normal'. Applies immediately."""
        mode_value = mode if mode is not None else mode_q
        mode = str(mode_value or "").strip().lower()
        if mode not in ("fast", "normal"):
            return {"ok": False, "error": f"Invalid mode '{mode}'. Use 'fast' or 'normal'."}

        rt_cfg = agent.config.get("realtime_profile", {})
        profile = rt_cfg.get(mode, {})
        if not profile:
            return {"ok": False, "error": f"Profile '{mode}' not configured."}

        rt_cfg["active"] = mode

        applied = {}
        if hasattr(agent, "apply_realtime_profile"):
            applied = agent.apply_realtime_profile(profile) or {}
        else:
            if hasattr(agent, "persona_num_predict"):
                agent.persona_num_predict = int(profile.get("num_predict_persona", agent.persona_num_predict))
            if hasattr(agent, "num_ctx"):
                agent.num_ctx = int(profile.get("num_ctx", agent.num_ctx))
            if hasattr(agent, "temperature"):
                agent.temperature = float(profile.get("temperature", agent.temperature))
            if hasattr(agent, "request_timeout"):
                agent.request_timeout = float(profile.get("request_timeout_s", agent.request_timeout))
            applied = {
                "num_predict_persona": getattr(agent, "persona_num_predict", None),
                "num_ctx": getattr(agent, "num_ctx", None),
                "temperature": getattr(agent, "temperature", None),
                "request_timeout_s": getattr(agent, "request_timeout", None),
            }

        return {
            "ok": True,
            "active": mode,
            "applied": applied,
        }

    # Removed legacy /executor/* endpoints since the queue is replaced by true Agentic loops

    return router

