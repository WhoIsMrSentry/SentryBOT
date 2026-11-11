from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.arbitrator import ExpressionArbiter
from ..services.state import SemanticExpressionEngine
from ..services.output_bridge import ExpressionOutputBridge

logger = logging.getLogger("expression.semantic.router")


class ExpressRequest(BaseModel):
    emotion: str = Field(..., description="Canonical emotion name (e.g., anger, joy, curiosity)")
    intensity: float = Field(1.0, ge=0.1, le=2.0, description="0.1=subtle, 1.0=normal, 2.0=extreme")
    duration_s: float = Field(3.0, ge=0.5, le=30.0)
    modalities: list[str] = Field(
        default_factory=lambda: ["leds", "oled", "voice", "head", "ears"],
        description="Subset of [leds, oled, voice, head, ears]",
    )
    text: Optional[str] = Field(None, description="Optional text to speak (requires voice modality)")
    language: str = Field("tr", description="BCP-47 language code for TTS")
    force: bool = Field(False, description="Skip visual lock and rate limiting")


def get_router(engine: SemanticExpressionEngine | None = None) -> APIRouter:
    """Create the expression API router.

    Args:
        engine: Optional legacy SemanticExpressionEngine (for backward compat).
                The new ExpressionArbiter is created with adapter clients during startup.
    """
    router = APIRouter(prefix="/expression", tags=["expression"])

    # Legacy bridge (still works for backward compat)
    bridge = ExpressionOutputBridge(engine) if engine else None
    arbiter: Optional[ExpressionArbiter] = None

    @router.get("/state")
    def state() -> Dict[str, Any]:
        if engine is None:
            return {"ok": False, "error": "no engine configured"}
        return engine.get_state()

    @router.get("/status")
    async def status() -> Dict[str, Any]:
        result: Dict[str, Any] = {"ok": True}
        if engine is not None:
            result["engine"] = engine.status()
        if bridge is not None:
            result["output"] = bridge.status()
        if arbiter is not None:
            try:
                result["arbiter"] = await arbiter.get_status()
            except Exception as exc:
                logger.warning("ExpressionArbiter get_status failed: %s", exc, exc_info=True)
                result["arbiter"] = {"active": False, "error": str(exc)}
        return result

    @router.get("/history")
    def history(limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
        if engine is None:
            return {"ok": False, "error": "no engine configured"}
        return engine.history(limit=limit)

    @router.post("/state")
    def set_state(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        if engine is None:
            return {"ok": False, "error": "no engine configured"}
        semantic = engine.apply(payload, source="api", reason=str(payload.get("reason") or "manual"))
        result = {"ok": True, "semantic": semantic}
        if bridge is not None:
            result["output"] = bridge.apply()
        return result

    @router.post("/event")
    def event(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        if engine is None:
            return {"ok": False, "error": "no engine configured"}
        event_type = str(payload.get("type") or payload.get("event") or "").strip()
        if not event_type:
            return {"ok": False, "error": "type is required"}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        semantic = engine.event(event_type, data)
        result = {"ok": True, "semantic": semantic}
        if bridge is not None:
            result["output"] = bridge.apply()
        return result

    @router.post("/express")
    async def express(req: ExpressRequest) -> Dict[str, Any]:
        """Express an emotion across all modalities atomically."""
        nonlocal arbiter
        if arbiter is None:
            raise HTTPException(status_code=503, detail="ExpressionArbiter not initialized")
        return await arbiter.express_emotion(
            emotion=req.emotion,
            intensity=req.intensity,
            duration_s=req.duration_s,
            modalities=req.modalities,
            text=req.text,
            language=req.language,
            force=req.force,
        )

    @router.post("/preview")
    async def preview(req: ExpressRequest) -> Dict[str, Any]:
        """Dry-run expression preview without driving hardware or altering visual locks."""
        nonlocal arbiter
        if arbiter is None:
            raise HTTPException(status_code=503, detail="ExpressionArbiter not initialized")
        return await arbiter.preview_emotion(
            emotion=req.emotion,
            intensity=req.intensity,
            duration_s=req.duration_s,
            modalities=req.modalities,
            text=req.text,
            language=req.language,
            force=req.force,
        )
    
    # Legacy bridge routes (kept for backward compat)
    @router.get("/output/status")
    def output_status() -> Dict[str, Any]:
        if bridge is None:
            return {"ok": False, "error": "no bridge configured"}
        return bridge.status()
    
    @router.get("/output/plan")
    def output_plan() -> Dict[str, Any]:
        if bridge is None:
            return {"ok": False, "error": "no bridge configured"}
        return bridge.plan()
    
    @router.post("/output/apply")
    def output_apply() -> Dict[str, Any]:
        if bridge is None:
            return {"ok": False, "error": "no bridge configured"}
        return bridge.apply()
    
    # Voice/vocab endpoints
    @router.get("/vocab")
    def vocab() -> Dict[str, Any]:
        from modules.common.emotion_vocab import get_vocab
        return {
            "ok": True,
            "default": get_vocab().default_canonical.value,
            "emotions": [e.value for e in get_vocab().all_canonical()],
        }
    
    @router.get("/render/{emotion}")
    def render(emotion: str) -> Dict[str, Any]:
        from modules.common.emotion_vocab import get_vocab
        return {"ok": True, "render": get_vocab().get_render_dict(emotion)}
    
    def set_arbiter(arb: ExpressionArbiter) -> None:
        """Inject the ExpressionArbiter after startup."""
        nonlocal arbiter
        arbiter = arb
    
    # Attach setter to router for startup hook
    router.set_arbiter = set_arbiter  # type: ignore
    
    return router