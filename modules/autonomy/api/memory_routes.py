from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter

from ..services.brain import AutonomyBrain


def register_memory_routes(router: APIRouter, brain: AutonomyBrain) -> None:
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
        if hasattr(brain, "get_world_memory_snapshot"):
            return brain.get_world_memory_snapshot()
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/schema")
    def get_world_memory_schema():
        if hasattr(brain, "get_world_memory_schema"):
            return brain.get_world_memory_schema()
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/recent")
    def get_world_memory_recent(kind: str = "", limit: int = 10):
        if hasattr(brain, "get_world_memory_recent"):
            return brain.get_world_memory_recent(kind or None, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/history")
    def get_world_memory_history(limit: int = 20):
        if hasattr(brain, "get_world_memory_history"):
            return brain.get_world_memory_history(limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/search")
    def search_world_memory(q: str = "", limit: int = 8):
        if hasattr(brain, "recall_world_memory"):
            return brain.recall_world_memory(q, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/context")
    def get_world_memory_context(q: str = "", limit: int = 8):
        if hasattr(brain, "get_world_memory_context"):
            return brain.get_world_memory_context(q, limit)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable", "context": ""}

    @router.post("/memory/observe")
    def observe_world_memory(payload: Dict[str, Any]):
        if hasattr(brain, "observe_world_memory"):
            return brain.observe_world_memory(payload or {}, source="api")
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.post("/memory/clear")
    def clear_world_memory(kind: str = ""):
        if hasattr(brain, "clear_world_memory"):
            return brain.clear_world_memory(kind or None)
        return {"ok": False, "available": False, "reason": "world_memory_unavailable"}

    @router.get("/memory/rag")
    def get_world_memory_rag():
        if hasattr(brain, "world_memory_rag_status"):
            return brain.world_memory_rag_status()
        return {"ok": False, "available": False, "reason": "world_memory_rag_unavailable"}
