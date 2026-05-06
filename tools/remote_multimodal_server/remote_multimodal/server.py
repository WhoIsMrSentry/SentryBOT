from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException

from .config import RuntimeConfig, load_runtime_config
from .engine import MultiModalEngine
from .models import AnalyzeRequest, RegisterFaceRequest

logger = logging.getLogger("remote_multimodal_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def create_app(runtime_cfg: Optional[RuntimeConfig] = None) -> FastAPI:
    cfg = runtime_cfg or load_runtime_config()
    engine = MultiModalEngine(cfg)
    app = FastAPI(title="SentryBOT Remote Multimodal Vision Server", version="0.2.0")

    def _require_auth(token: Optional[str]) -> None:
        if cfg.auth_token and cfg.auth_token != "changeme" and token != cfg.auth_token:
            raise HTTPException(status_code=401, detail="invalid auth token")

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {
            "ok": True,
            "auth_enabled": bool(cfg.auth_token and cfg.auth_token != "changeme"),
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
            },
        }

    @app.post("/vision/analyze")
    def analyze(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        return engine.analyze(req.image_b64)

    @app.post("/vision/register_face")
    def register_face(req: RegisterFaceRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        name = str(req.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        return engine.register_face(name=name, image_b64=req.image_b64)

    return app


def run_app() -> None:
    import uvicorn

    cfg = load_runtime_config()
    uvicorn.run("app:app", host=cfg.host, port=cfg.port)
