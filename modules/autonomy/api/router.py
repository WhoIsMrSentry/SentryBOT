from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

from ..services.brain import AutonomyBrain
from ..services import palette_store
from .memory_routes import register_memory_routes
from .companion_routes import register_companion_routes


class ActionPayload(BaseModel):
    text: str = ""
    actions: List[Dict[str, Any]] | None = None
    raw: str | None = None
    speak: bool = False


class PaletteBody(BaseModel):
    rgb: List[int]


class SpeechFinalPayload(BaseModel):
    text: str = ""
    language: str = ""
    final: bool = True


def get_router(brain: AutonomyBrain) -> APIRouter:
    router = APIRouter(prefix="/autonomy", tags=["autonomy"])

    register_memory_routes(router, brain)
    register_companion_routes(router, brain)

    @router.get("/state")
    def get_state():
        # Copy: never hand out the live state dict over HTTP (R8).
        return dict(brain.state)

    @router.get("/mood")
    def get_mood():
        # Snapshot: never expose the live mood dict over HTTP (C2).
        return brain.mood.snapshot()

    @router.post("/express/{emotion}")
    def express_emotion(emotion: str):
        brain.express(emotion)
        return {"status": "ok", "emotion": emotion}

    @router.get("/audio-event")
    def get_audio_event_needs():
        if hasattr(brain, "get_audio_event_needs_snapshot"):
            return brain.get_audio_event_needs_snapshot()
        return {"ok": False, "available": False, "reason": "audio_event_bridge_unavailable"}

    @router.post("/audio-event/observe")
    def observe_audio_event_needs(payload: Dict[str, Any]):
        if hasattr(brain, "observe_audio_event_for_needs"):
            return brain.observe_audio_event_for_needs(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "audio_event_bridge_unavailable"}

    @router.get("/vision-context")
    def get_vision_context_needs():
        if hasattr(brain, "get_vision_context_needs_snapshot"):
            return brain.get_vision_context_needs_snapshot()
        return {"ok": False, "available": False, "reason": "vision_context_bridge_unavailable"}

    @router.post("/vision-context/observe")
    def observe_vision_context_needs(payload: Dict[str, Any]):
        if hasattr(brain, "observe_vision_context_for_needs"):
            return brain.observe_vision_context_for_needs(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "vision_context_bridge_unavailable"}

    @router.get("/sound-interrupt")
    def get_sound_interrupt():
        if hasattr(brain, "get_sound_interrupt_snapshot"):
            return brain.get_sound_interrupt_snapshot()
        return {"ok": False, "available": False, "reason": "sound_interrupt_unavailable"}

    @router.post("/sound-interrupt")
    def handle_sound_interrupt(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "handle_sound_interrupt"):
            return brain.handle_sound_interrupt(payload or {})
        return {"ok": False, "available": False, "reason": "sound_interrupt_unavailable"}

    @router.get("/navigation/status")
    def get_navigation_status():
        if hasattr(brain, "get_safe_navigation_status"):
            return brain.get_safe_navigation_status()
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.get("/navigation/places")
    def list_navigation_places():
        if hasattr(brain, "list_safe_places"):
            return brain.list_safe_places()
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.post("/navigation/places/learn")
    def learn_navigation_place(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "learn_safe_place"):
            return brain.learn_safe_place(payload or {})
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.post("/navigation/rest-corner")
    def execute_rest_corner(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "execute_safe_rest_corner"):
            return brain.execute_safe_rest_corner(payload or {})
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.post("/interaction")
    def report_interaction():
        brain.interaction_occurred(source="api")
        return {"status": "ok", "mood": int(brain.mood["happiness"])}

    @router.post("/speech")
    def speech_final(payload: SpeechFinalPayload):
        if not payload.final:
            return {"ok": True, "handled": False, "reason": "not_final"}
        brain.interaction_occurred(source="speech")
        handled = brain.on_speech_final(payload.text, payload.language)
        return {"ok": True, "handled": handled}

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

    @router.get("/assets/status")
    def get_model_assets_status():
        if hasattr(brain, "get_model_asset_status"):
            return brain.get_model_asset_status()
        return {"ok": False, "available": False, "reason": "asset_truth_unavailable"}

    @router.get("/pi-runtime/status")
    def get_pi_runtime_status():
        if hasattr(brain, "get_pi_runtime_status"):
            return brain.get_pi_runtime_status()
        return {"ok": False, "available": False, "reason": "pi_runtime_unavailable"}

    @router.get("/navigation/topomap")
    def get_navigation_topomap():
        if hasattr(brain, "get_navigation_topomap"):
            return brain.get_navigation_topomap()
        return {"ok": False, "available": False, "reason": "topomap_unavailable"}

    @router.post("/navigation/topomap/learn")
    def learn_navigation_topomap_place(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "learn_navigation_topomap_place"):
            return brain.learn_navigation_topomap_place(payload or {})
        return {"ok": False, "available": False, "reason": "topomap_unavailable"}

    @router.post("/navigation/goal")
    def execute_navigation_goal(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "execute_navigation_goal"):
            return brain.execute_navigation_goal(payload or {})
        return {"ok": False, "available": False, "reason": "topomap_unavailable"}

    @router.get("/owner/status")
    def get_owner_learning_status():
        if hasattr(brain, "get_owner_learning_status"):
            return brain.get_owner_learning_status()
        return {"ok": False, "available": False, "reason": "owner_learning_unavailable"}

    @router.post("/owner/learn")
    def learn_owner_person(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "learn_owner_person"):
            return brain.learn_owner_person(payload or {})
        return {"ok": False, "available": False, "reason": "owner_learning_unavailable"}

    @router.post("/owner/identify")
    def identify_owner_person(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "identify_owner_person"):
            return brain.identify_owner_person(payload or {})
        return {"ok": False, "available": False, "reason": "owner_learning_unavailable"}

    return router
