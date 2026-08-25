from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException

from .config import RuntimeConfig, load_runtime_config
from .engine import MultiModalEngine
from .models import AnalyzeRequest, OcrRequest, RegisterFaceRequest

logger = logging.getLogger("remote_multimodal_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def create_app(runtime_cfg: Optional[RuntimeConfig] = None) -> FastAPI:
    cfg = runtime_cfg or load_runtime_config()
    engine = MultiModalEngine(cfg)
    app = FastAPI(title="SentryBOT Remote Multimodal Vision Server", version="0.2.0")

    def _require_auth(token: Optional[str]) -> None:
        if cfg.auth_token and token != cfg.auth_token:
            raise HTTPException(status_code=401, detail="invalid auth token")

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {
            "ok": True,
            "auth_enabled": bool(cfg.auth_token),
            "config": {
                "runtime_profile": cfg.runtime_profile,
                "detector_backend": cfg.detector_backend,
                "yolo_model": cfg.yolo_model,
                "yolo_conf": cfg.yolo_conf,
                "yolo_imgsz": cfg.yolo_imgsz,
                "motion_threshold": cfg.motion_threshold,
                "scene_change_threshold": cfg.scene_change_threshold,
                "face_db_path": cfg.face_db_path,
                "enable_face_recognition": cfg.enable_face_recognition,
                "enable_age_emotion": cfg.enable_age_emotion,
                "enable_qwen_vlm": cfg.enable_qwen_vlm,
                "qwen_endpoint": cfg.qwen_endpoint,
                "qwen_primary_model": cfg.qwen_primary_model,
                "qwen_fallback_model": cfg.qwen_fallback_model,
                "qwen_timeout_s": cfg.qwen_timeout_s,
                "enable_advanced_caption": cfg.enable_advanced_caption,
                "advanced_caption_model": cfg.advanced_caption_model,
                "task_split_endpoints": True,
                "cheap_endpoint": "/vision/analyze/cheap",
                "semantic_endpoint": "/vision/analyze/semantic",
            },
        }

    @app.post("/vision/analyze")
    def analyze(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        return engine.analyze(
            req.image_b64,
            requested_tasks=req.requested_tasks,
            run_semantic_vlm=req.run_semantic_vlm,
            semantic_reason=req.semantic_reason or "",
            request_id=req.request_id or "",
            question=req.question or "",
            task_mode=req.mode or "legacy",
        )

    @app.post("/vision/analyze/cheap")
    def analyze_cheap(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        return engine.analyze_cheap(
            req.image_b64,
            requested_tasks=req.requested_tasks,
            semantic_reason=req.semantic_reason or "cheap_poll",
            request_id=req.request_id or "",
            question=req.question or "",
        )

    @app.post("/vision/analyze/semantic")
    def analyze_semantic(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        return engine.analyze_semantic(
            req.image_b64,
            requested_tasks=req.requested_tasks,
            semantic_reason=req.semantic_reason or "semantic_request",
            request_id=req.request_id or "",
            question=req.question or "",
        )

    @app.post("/vision/register_face")
    def register_face(req: RegisterFaceRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        name = str(req.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        return engine.register_face(name=name, image_b64=req.image_b64)

    @app.post("/vision/ocr")
    def ocr(req: OcrRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        try:
            frame = engine.decode_image(req.image_b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return engine.ocr_frame(frame)

    return app


def run_app() -> None:
    import uvicorn

    cfg = load_runtime_config()
    public_bind = str(cfg.host).strip().lower() in {"0.0.0.0", "::", "[::]"}
    if public_bind and not str(cfg.auth_token or "").strip():
        raise RuntimeError("MM_AUTH_TOKEN or SENTRYBOT_VLM_AUTH_TOKEN is required when remote_multimodal binds to a public interface")
    uvicorn.run("app:app", host=cfg.host, port=cfg.port)
