from __future__ import annotations

import hmac
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class RemoteDetectionItem(BaseModel):
    label: str = Field(default="unknown", min_length=1, max_length=64)
    name: str = Field(default="Unknown", max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: List[float] = Field(default_factory=list, max_length=4)
    distance_m: float | None = Field(default=None, ge=0.0, le=100.0)
    emotion: str = Field(default="", max_length=64)


class IngestResultsPayload(BaseModel):
    objects: List[Dict[str, Any]] = Field(default_factory=list, max_length=200)
    timestamp: float | None = None


def get_config_router(processor: Any, base_url: str) -> APIRouter:
    r = APIRouter(tags=["vlm-config"])

    @r.get("/mode", tags=["control"], summary="Get active mode/profile flags")
    def get_mode():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        modes = processor.get_modes() if hasattr(processor, "get_modes") else {}
        profiles = processor.list_profiles() if hasattr(processor, "list_profiles") else []
        return {
            "ok": True,
            "processing_mode": getattr(processor, "processing_mode", "unknown"),
            "modes": modes,
            "profiles": profiles,
        }

    @r.post("/mode", tags=["control"], summary="Set processing mode and/or mode flags")
    def set_mode(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be object")

        out: dict = {"ok": True}

        processing_mode = body.get("processing_mode")
        if processing_mode is not None and hasattr(processor, "set_processing_mode"):
            out["processing_mode"] = processor.set_processing_mode(str(processing_mode))

        profile = body.get("profile")
        if profile is not None and hasattr(processor, "apply_mode_profile"):
            out["profile"] = processor.apply_mode_profile(str(profile))

        modes = body.get("modes")
        if isinstance(modes, dict) and hasattr(processor, "set_modes"):
            out["modes_update"] = processor.set_modes(modes)

        out["modes"] = processor.get_modes() if hasattr(processor, "get_modes") else {}
        out["processing_mode_current"] = getattr(processor, "processing_mode", "unknown")
        return out

    @r.get("/modes/categories", tags=["control"], summary="Get hierarchical mode categories")
    def get_mode_categories():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "get_mode_categories"):
            raise HTTPException(status_code=501, detail="mode_categories not supported")
        return {"ok": True, "mode_categories": processor.get_mode_categories()}

    @r.post("/modes/categories", tags=["control"], summary="Patch hierarchical mode categories")
    def patch_mode_categories(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "set_mode_categories"):
            raise HTTPException(status_code=501, detail="mode_categories not supported")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be object")
        return processor.set_mode_categories(body)

    @r.get("/profile", tags=["control"], summary="Get realtime latency profile")
    def get_profile():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if hasattr(processor, "get_realtime_profile_status"):
            return processor.get_realtime_profile_status()
        return {"ok": False, "error": "profile control not available"}

    @r.post("/profile/switch", tags=["control"], summary="Switch realtime latency profile")
    def switch_profile(body: dict):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        mode = str((body or {}).get("mode", "")).strip().lower()
        if not mode:
            raise HTTPException(status_code=400, detail="mode required")
        if hasattr(processor, "apply_realtime_profile"):
            return processor.apply_realtime_profile(mode)
        return {"ok": False, "error": "profile control not available"}

    @r.post("/blind/start", tags=["assistive"], summary="Start assistive blind mode")
    def start_blind_mode():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not getattr(processor, "_camera_hardware_available", False):
            raise HTTPException(status_code=503, detail="camera_disabled")

        processor.blind_mode_enabled = True
        processor.start_stream_processing()
        return {"status": "Blind mode started"}

    @r.post("/blind/stop", tags=["assistive"], summary="Stop assistive blind mode")
    def stop_blind_mode():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")

        processor.blind_mode_enabled = False
        return {"status": "Blind mode stopped"}

    @r.get("/results/latest", tags=["remote"], summary="Get last cached detections")
    def latest_results(limit: int = 10):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "latest_results"):
            raise HTTPException(status_code=503, detail="Vision processor missing latest_results interface")
        limit = max(0, int(limit))
        results = list(getattr(processor, "latest_results", []) or [])
        if limit:
            results = results[:limit]
        return {"results": results, "count": len(results)}

    @r.post("/results", tags=["remote"], summary="Ingest remote detection results")
    def ingest_results(request: Request, payload: IngestResultsPayload):
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not hasattr(processor, "config") or not hasattr(processor, "ingest_remote_results"):
            raise HTTPException(status_code=503, detail="Vision processor missing remote ingestion interface")

        cfg_remote = processor.config.get("remote", {}) if isinstance(processor.config, dict) else {}
        if not cfg_remote.get("accept_results", True):
            raise HTTPException(status_code=403, detail="Remote result ingestion disabled")

        cfg_tok = str(cfg_remote.get("auth_token") or "").strip()
        if cfg_tok in {"", "changeme"}:
            cfg_tok = ""
        env_tok = str(
            os.getenv("SENTRYBOT_VLM_AUTH_TOKEN") or os.getenv("MM_AUTH_TOKEN") or ""
        ).strip()
        if env_tok in {"", "changeme"}:
            env_tok = ""
        auth_required = cfg_tok or env_tok
        if not auth_required:
            raise HTTPException(status_code=401, detail="VLM auth token not configured")

        provided = str(request.headers.get("X-Auth-Token") or "").strip()
        if not provided or not hmac.compare_digest(auth_required, provided):
            raise HTTPException(status_code=401, detail="Invalid auth token")

        validated_objects: List[Dict[str, Any]] = []
        for item in payload.objects:
            if not isinstance(item, dict):
                continue
            model_item = RemoteDetectionItem(
                label=str(item.get("label") or item.get("name") or "unknown")[:64],
                name=str(item.get("name") or "Unknown")[:64],
                confidence=max(0.0, min(1.0, float(item.get("confidence", item.get("conf", 0.0)) or 0.0))),
                bbox=[float(v) for v in (item.get("bbox") or item.get("box") or [])[:4]],
                distance_m=(
                    float(item["distance_m"])
                    if item.get("distance_m") is not None
                    else (float(item["distance"]) if item.get("distance") is not None else None)
                ),
                emotion=str(item.get("emotion") or item.get("face_emotion") or "")[:64],
            )
            validated_objects.append(model_item.model_dump())

        summary = processor.ingest_remote_results(validated_objects)
        return {"ok": True, "summary": summary}

    @r.get("/context/latest", tags=["vision"], summary="Get latest visual context cache")
    def get_context_latest():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.has_vision_context():
            return {"available": False, "context": None, "reason": "no_vision_context"}
        ctx = processor.get_latest_visual_context()
        if ctx is None:
            return {"available": False, "context": None, "reason": "No context cached yet"}
        return {"available": True, "context": ctx}

    @r.post("/context/refresh", tags=["vision"], summary="Refresh visual context (trigger VLM analysis)")
    def refresh_context():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if not processor.is_local_camera_available():
            return {"ok": False, "context_available": False, "context": None, "reason": "camera_unavailable"}

        if hasattr(processor, "refresh_visual_context"):
            ctx = processor.refresh_visual_context()
        else:
            ctx = processor.get_latest_visual_context()
        return {"ok": True, "context_available": ctx is not None, "context": ctx}

    @r.get("/video_feed", tags=["stream"], summary="Annotated MJPEG stream (local)")
    def video_feed():
        if not processor:
            raise HTTPException(status_code=503, detail="Vision processor not initialized")
        if processor.processing_mode != "local":
            raise HTTPException(status_code=400, detail="Video feed not available in remote mode")
        processor.start_stream_processing()
        from fastapi.responses import StreamingResponse
        return StreamingResponse(processor.generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    return r
