from fastapi import APIRouter, Body
from typing import Dict, Any


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
