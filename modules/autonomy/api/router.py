from fastapi import APIRouter, Depends
from ..services.brain import AutonomyBrain

def get_router(brain: AutonomyBrain) -> APIRouter:
    router = APIRouter(prefix="/autonomy", tags=["autonomy"])

    @router.get("/state")
    def get_state():
        return brain.state

    @router.post("/interaction")
    def report_interaction():
        """Report that an interaction occurred (resets boredom timer)"""
        brain.interaction_occurred()
        return {"status": "ok", "mood": brain.state["happiness"]}

    return router
