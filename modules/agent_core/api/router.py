from fastapi import APIRouter, Body
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

    # Removed legacy /executor/* endpoints since the queue is replaced by true Agentic loops

    return router
