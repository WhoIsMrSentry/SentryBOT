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


class SpeechFinalPayload(BaseModel):
    text: str = ""
    language: str = ""
    final: bool = True

def get_router(brain: AutonomyBrain) -> APIRouter:
    router = APIRouter(prefix="/autonomy", tags=["autonomy"])

    @router.get("/state")
    def get_state():
        return brain.state

    @router.get("/needs")
    def get_needs():
        """Return the central companion needs snapshot."""
        if hasattr(brain, "get_needs_snapshot"):
            return brain.get_needs_snapshot()
        return {"ok": False, "available": False, "reason": "needs_snapshot_unavailable"}

    @router.get("/goal")
    def get_goal():
        """Return the current semantic companion goal plan."""
        if hasattr(brain, "get_companion_goal_snapshot"):
            return brain.get_companion_goal_snapshot()
        return {"ok": False, "available": False, "reason": "goal_snapshot_unavailable"}

    @router.get("/memory/needs-bias")
    def get_memory_needs_bias():
        if hasattr(brain, "get_memory_needs_bias_snapshot"):
            return brain.get_memory_needs_bias_snapshot()
        return {"ok": False, "available": False, "reason": "memory_needs_bias_unavailable"}

    @router.post("/memory/needs-bias/evaluate")
    def evaluate_memory_needs_bias(payload: Dict[str, Any]):
        if hasattr(brain, "evaluate_memory_needs_bias"):
            return brain.evaluate_memory_needs_bias(payload or {})
        return {"ok": False, "available": False, "reason": "memory_needs_bias_unavailable"}

    @router.get("/memory/decision-shadow")
    def get_memory_decision_shadow():
        if hasattr(brain, "get_memory_decision_shadow"):
            return brain.get_memory_decision_shadow()
        return {"ok": False, "available": False, "reason": "memory_decision_shadow_unavailable"}

    @router.post("/memory/decision-shadow/evaluate")
    def evaluate_memory_decision_shadow(payload: Dict[str, Any]):
        if hasattr(brain, "evaluate_memory_decision_shadow"):
            return brain.evaluate_memory_decision_shadow(payload or {})
        return {"ok": False, "available": False, "reason": "memory_decision_shadow_unavailable"}

    @router.get("/memory/autowrite")
    def get_world_memory_autowrite():
        if hasattr(brain, "get_world_memory_autowrite_snapshot"):
            return brain.get_world_memory_autowrite_snapshot()
        return {"ok": False, "available": False, "reason": "world_memory_autowrite_unavailable"}

    @router.post("/memory/autowrite")
    def observe_world_memory_from_context(payload: Dict[str, Any]):
        source_type = ""
        context = payload or {}
        if isinstance(payload, dict):
            source_type = str(payload.get("source_type") or payload.get("type") or payload.get("source") or "")
            context = payload.get("context") if isinstance(payload.get("context"), dict) else payload
        if hasattr(brain, "observe_context_world_memory"):
            return brain.observe_context_world_memory(source_type or "api", context or {})
        return {"ok": False, "available": False, "reason": "world_memory_autowrite_unavailable"}

    @router.get("/memory")
    def get_world_memory():
        """Return world-memory counts and recent semantic facts."""
        if hasattr(brain, "get_world_memory_snapshot"):
            return brain.get_world_memory_snapshot()
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/schema")
    def get_world_memory_schema():
        """Return the local semantic world-memory schema."""
        if hasattr(brain, "get_world_memory_schema"):
            return brain.get_world_memory_schema()
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/recent")
    def get_world_memory_recent(kind: str = "", limit: int = 10):
        """Return recent world-memory items, optionally filtered by kind."""
        if hasattr(brain, "get_world_memory_recent"):
            return brain.get_world_memory_recent(kind or None, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/history")
    def get_world_memory_history(limit: int = 20):
        """Return compact memory write history."""
        if hasattr(brain, "get_world_memory_history"):
            return brain.get_world_memory_history(limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/search")
    def search_world_memory(q: str = "", limit: int = 8):
        """Recall semantic world-memory items for RAG."""
        if hasattr(brain, "recall_world_memory"):
            return brain.recall_world_memory(q, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/context")
    def get_world_memory_context(q: str = "", limit: int = 8):
        """Return compact RAG context text for the agent."""
        if hasattr(brain, "get_world_memory_context"):
            return brain.get_world_memory_context(q, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable", "context": ""}

    @router.post("/memory/observe")
    def observe_world_memory(payload: Dict[str, Any]):
        """Store a semantic observation in world memory."""
        if hasattr(brain, "observe_world_memory"):
            return brain.observe_world_memory(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.post("/memory/clear")
    def clear_world_memory(kind: str = ""):
        """Clear world memory; pass kind to clear one bucket."""
        if hasattr(brain, "clear_world_memory"):
            return brain.clear_world_memory(kind or None)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}



    @router.get("/memory/rag")
    def get_world_memory_rag():
        if hasattr(brain, "world_memory_rag_status"):
            return brain.world_memory_rag_status()
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.get("/memory/rag/recent")
    def get_world_memory_rag_recent(kind: str = "", limit: int = 10):
        if hasattr(brain, "world_memory_rag_recent"):
            return brain.world_memory_rag_recent(kind or "", limit)
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.post("/memory/rag/observe")
    def observe_world_memory_rag(payload: Dict[str, Any]):
        if hasattr(brain, "world_memory_rag_observe"):
            return brain.world_memory_rag_observe(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.get("/memory/rag/recall")
    def recall_world_memory_rag(query: str = "", limit: int = 8):
        if hasattr(brain, "world_memory_rag_recall"):
            return brain.world_memory_rag_recall(query or "", limit)
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.get("/memory/rag/context")
    def context_world_memory_rag(query: str = "", limit: int = 8):
        if hasattr(brain, "world_memory_rag_context"):
            return brain.world_memory_rag_context(query or "", limit)
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.post("/memory/rag/forget")
    def forget_world_memory_rag(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "world_memory_rag_forget"):
            return brain.world_memory_rag_forget(payload or {})
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}

    @router.get("/living/status")
    def get_living_companion_status():
        if hasattr(brain, "get_living_companion_status"):
            return brain.get_living_companion_status()
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.get("/living/needs")
    def get_living_companion_needs():
        if hasattr(brain, "get_living_companion_status"):
            status = brain.get_living_companion_status()
            return ((status.get("needs") or {}).get("last") or status.get("needs") or status)
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.post("/living/tick")
    def tick_living_companion(payload: Dict[str, Any] | None = None, force: bool = False):
        if hasattr(brain, "tick_living_companion"):
            return brain.tick_living_companion(payload or {}, force=force)
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.post("/living/vision")
    def observe_living_vision(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "observe_living_vision"):
            return brain.observe_living_vision(payload or {})
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.post("/living/audio")
    def observe_living_audio(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "observe_living_audio"):
            return brain.observe_living_audio(payload or {})
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.post("/living/boredom")
    def force_living_boredom(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "force_boredom_behavior"):
            return brain.force_boredom_behavior(payload or {})
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.post("/living/sound-interrupt")
    def living_sound_interrupt(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "sound_interrupt_wake"):
            return brain.sound_interrupt_wake(payload or {})
        return {"ok": False, "available": False, "reason": "living_companion_unavailable"}

    @router.get("/navigation/safe-places")
    def list_navigation_safe_places():
        if hasattr(brain, "living_companion"):
            return brain.living_companion.navigation.list_places()
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.post("/navigation/safe-places")
    def learn_navigation_safe_place(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "living_companion"):
            return brain.living_companion.navigation.learn_place(payload or {})
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.post("/navigation/rest-corner")
    def navigation_rest_corner(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "rest_in_safe_corner"):
            return brain.rest_in_safe_corner(payload or {})
        return {"ok": False, "available": False, "reason": "safe_navigation_unavailable"}

    @router.get("/audio-context")
    def get_audio_event_needs():
        """Return latest audio/wakeword context used by companion needs."""
        if hasattr(brain, "get_audio_event_needs_snapshot"):
            return brain.get_audio_event_needs_snapshot()
        return {"ok": False, "available": False, "reason": "audio_event_bridge_unavailable"}

    @router.post("/audio-context/observe")
    def observe_audio_event_needs(payload: Dict[str, Any]):
        """Store a semantic audio event for needs selection."""
        if hasattr(brain, "observe_audio_event_for_needs"):
            return brain.observe_audio_event_for_needs(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "audio_event_bridge_unavailable"}

    @router.get("/vision-context")
    def get_vision_context_needs():
        """Return latest vision context used by the companion needs bridge."""
        if hasattr(brain, "get_vision_context_needs_snapshot"):
            return brain.get_vision_context_needs_snapshot()
        return {"ok": False, "available": False, "reason": "vision_context_bridge_unavailable"}

    @router.post("/vision-context/observe")
    def observe_vision_context_needs(payload: Dict[str, Any]):
        """Store a semantic camera/VLM observation for needs selection."""
        if hasattr(brain, "observe_vision_context_for_needs"):
            return brain.observe_vision_context_for_needs(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "vision_context_bridge_unavailable"}

    @router.get("/living-needs")
    def get_living_needs():
        if hasattr(brain, "get_living_needs_snapshot"):
            return brain.get_living_needs_snapshot()
        return {"ok": False, "available": False, "reason": "living_needs_unavailable"}

    @router.post("/living-needs/tick")
    def tick_living_needs():
        if hasattr(brain, "tick_living_needs"):
            return brain.tick_living_needs()
        return {"ok": False, "available": False, "reason": "living_needs_unavailable"}

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

    @router.get("/goal/auto")
    def get_goal_auto_execute_gate():
        """Return companion auto-execute gate status and last decision."""
        if hasattr(brain, "get_companion_auto_execute_snapshot"):
            return brain.get_companion_auto_execute_snapshot()
        return {"ok": False, "available": False, "reason": "auto_execute_gate_unavailable"}

    @router.post("/goal/auto/tick")
    def tick_goal_auto_execute(payload: Dict[str, Any] | None = None, force: bool = False):
        """Evaluate the current semantic goal through the auto-execute gate.

        Defaults are PC-safe and dry-run only. Use force=true only for manual
        validation of the selected plan; it still stays dry-run unless config
        explicitly allows real hardware.
        """
        if hasattr(brain, "tick_companion_auto_execute"):
            return brain.tick_companion_auto_execute(payload or {}, force=force)
        return {"ok": False, "available": False, "reason": "auto_execute_gate_unavailable"}

    @router.get("/goal/execution")
    def get_goal_execution():
        """Return the last safe companion goal execution/dry-run."""
        if hasattr(brain, "get_companion_goal_execution_snapshot"):
            return brain.get_companion_goal_execution_snapshot()
        return {"ok": False, "available": False, "reason": "goal_executor_unavailable"}

    @router.post("/goal/execute")
    def execute_goal(payload: Dict[str, Any] | None = None):
        """Dry-run or execute the current semantic goal plan.

        PC tests and default config block real hardware. Use this endpoint first
        to inspect the safe action execution steps.
        """
        if hasattr(brain, "execute_companion_goal"):
            return brain.execute_companion_goal(payload or {})
        return {"ok": False, "available": False, "reason": "goal_executor_unavailable"}

    @router.post("/goal/simulate")
    def simulate_goal(payload: Dict[str, Any]):
        """Simulate needs -> goal without executing hardware."""
        if not hasattr(brain, "goal_selector"):
            return {"ok": False, "available": False, "reason": "goal_selector_unavailable"}
        return brain.goal_selector.select(payload or {})

    @router.post("/interaction")
    def report_interaction():
        """Report that an interaction occurred (resets boredom timer)"""
        brain.interaction_occurred(source="api")
        return {"status": "ok", "mood": int(brain.mood["happiness"])}

    @router.post("/speech")
    def speech_final(payload: SpeechFinalPayload):
        """Event-driven speech ingestion: process a final transcript immediately."""
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


    # BEGIN BATCH04 PI HARDWARE OWNER TOPO ROUTES
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

    @router.post("/scenario/companion-e2e")
    def run_companion_e2e_scenario(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "run_companion_e2e_scenario"):
            return brain.run_companion_e2e_scenario(payload or {})
        return {"ok": False, "available": False, "reason": "scenario_unavailable"}
    # END BATCH04 PI HARDWARE OWNER TOPO ROUTES

    return router
