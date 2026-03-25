from fastapi import APIRouter, Body
from typing import Dict, Any


def get_router(agent) -> APIRouter:
    router = APIRouter(tags=["Agent Core"])

    @router.get("/healthz")
    def healthz():
        return {"ok": True, "state": agent.executor.state.name}

    @router.post("/step")
    def step(query: str = Body(embed=True)):
        """Tek bir agent adımı çalıştır (ReAct + Tool Calling + Safety)."""
        result = agent.step(query)
        return result or {"text": "", "thoughts": "idle", "actions": []}

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

    @router.post("/executor/interrupt")
    def interrupt():
        """Mevcut plan kuyruğunu durdur ve motorları kes."""
        agent.executor.interrupt()
        return {"ok": True, "state": "INTERRUPTED"}

    @router.post("/executor/resume")
    def resume():
        """Kesilen çalışmayı devam ettir."""
        agent.executor.resume()
        return {"ok": True, "state": agent.executor.state.name}

    return router
