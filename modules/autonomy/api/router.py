from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

from ..services.brain import AutonomyBrain
from ..services import palette_store


class ActionPayload(BaseModel):
    text: str = ""
    actions: List[Dict[str, Any]] | None = None
    raw: str | None = None
    speak: bool = False


class PaletteBody(BaseModel):
    rgb: List[int]

def get_router(brain: AutonomyBrain) -> APIRouter:
    router = APIRouter(prefix="/autonomy", tags=["autonomy"])

    @router.get("/state")
    def get_state():
        return brain.state

    @router.post("/interaction")
    def report_interaction():
        """Report that an interaction occurred (resets boredom timer)"""
        brain.interaction_occurred(source="api")
        return {"status": "ok", "mood": int(brain.mood["happiness"])}

    @router.post("/apply_actions")
    def apply_actions(payload: ActionPayload):
        cleaned = brain.apply_llm_response(payload.text, payload.actions, payload.raw, speak=payload.speak)
        return {"ok": True, "text": cleaned}

    @router.get("/lights/palettes")
    def list_palettes():
        return {"ok": True, "items": palette_store.list_palettes()}

    @router.post("/lights/palettes/{name}")
    def set_palette(name: str, body: PaletteBody):
        if not name:
            raise HTTPException(status_code=400, detail="palette name required")
        try:
            palettes = palette_store.set_palette(name, body.rgb)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        brain.update_palettes(palettes)
        return {"ok": True, "items": palettes}

    @router.delete("/lights/palettes/{name}")
    def delete_palette(name: str):
        if not name:
            raise HTTPException(status_code=400, detail="palette name required")
        try:
            palettes = palette_store.remove_palette(name)
        except KeyError:
            raise HTTPException(status_code=404, detail="palette not found")
        brain.update_palettes(palettes)
        return {"ok": True, "items": palettes}

    @router.post("/start")
    def start_brain():
        brain.start()
        return {"ok": True}

    @router.post("/stop")
    def stop_brain():
        brain.stop()
        return {"ok": True}

    return router
