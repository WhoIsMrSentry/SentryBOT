from fastapi import APIRouter, Query


def get_state_router(agent) -> APIRouter:
    router = APIRouter(tags=["agent-state"])

    @router.get("/world_state")
    def world_state():
        return agent.world_state.get_state()

    @router.get("/memory/search")
    def search_memory(query: str, limit: int = 5):
        return {"results": agent.memory.search_memory(query, limit)}

    @router.get("/slam/location")
    def get_location():
        return {"location": agent.slam.get_location()}

    @router.get("/slam/pathfind")
    def pathfind(destination: str):
        path = agent.slam.pathfind(destination)
        return {"destination": destination, "path": path}

    return router
