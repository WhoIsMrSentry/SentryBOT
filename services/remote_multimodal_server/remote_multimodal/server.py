from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import logging
import threading
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
import requests

from .config import RuntimeConfig, load_runtime_config
from .engine import MultiModalEngine
from .models import AnalyzeRequest, OcrRequest, RegisterFaceRequest

logger = logging.getLogger("remote_multimodal_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

_QWEN_PROBE_CACHE: Dict[str, Any] = {"ts": 0.0, "endpoint": "", "result": None}
_QWEN_PROBE_LOCK = threading.Lock()
_QWEN_PROBE_TTL_S = 15.0


def _vram_summary() -> Dict[str, Any]:
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return {"available": False, "reason": "cuda_unavailable"}
        free_b, total_b = torch.cuda.mem_get_info()
        used_b = max(0, int(total_b) - int(free_b))
        return {
            "available": True,
            "free_mb": round(int(free_b) / (1024 * 1024), 1),
            "used_mb": round(used_b / (1024 * 1024), 1),
            "total_mb": round(int(total_b) / (1024 * 1024), 1),
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _ollama_tags_url(qwen_endpoint: str) -> str:
    ep = str(qwen_endpoint or "").strip().rstrip("/")
    for suffix in ("/api/chat", "/api/generate", "/api/tags"):
        if ep.endswith(suffix):
            return ep[: -len(suffix)] + "/api/tags"
    return (ep + "/api/tags") if ep else ""


def _qwen_health_cached(cfg: RuntimeConfig) -> Dict[str, Any]:
    if not cfg.enable_qwen_vlm:
        return {"enabled": False, "reachable": False, "cached": False}
    tags_url = _ollama_tags_url(cfg.qwen_endpoint)
    if not tags_url:
        return {"enabled": True, "reachable": False, "cached": False, "reason": "endpoint_missing"}
    now = time.monotonic()
    with _QWEN_PROBE_LOCK:
        cached = _QWEN_PROBE_CACHE.get("result")
        if (
            cached is not None
            and _QWEN_PROBE_CACHE.get("endpoint") == tags_url
            and (now - float(_QWEN_PROBE_CACHE.get("ts", 0.0))) < _QWEN_PROBE_TTL_S
        ):
            return {**cached, "cached": True}
    reachable = False
    err = ""
    try:
        resp = requests.get(tags_url, timeout=0.8)
        reachable = resp.status_code == 200
        if not reachable:
            err = f"http_{resp.status_code}"
    except Exception as exc:
        err = str(exc)
    result = {"enabled": True, "reachable": reachable, "endpoint": tags_url, "ttl_s": _QWEN_PROBE_TTL_S}
    if err:
        result["error"] = err
    with _QWEN_PROBE_LOCK:
        _QWEN_PROBE_CACHE["ts"] = now
        _QWEN_PROBE_CACHE["endpoint"] = tags_url
        _QWEN_PROBE_CACHE["result"] = result
    return {**result, "cached": False}


def create_app(runtime_cfg: Optional[RuntimeConfig] = None, *, lazy_backends: bool = False) -> FastAPI:
    cfg = runtime_cfg or load_runtime_config()
    engine = MultiModalEngine(cfg, lazy_backends=lazy_backends)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        engine.ensure_ready()
        yield

    app = FastAPI(title="SentryBOT Remote Multimodal Vision Server", version="0.2.0", lifespan=lifespan)

    def _require_auth(token: Optional[str]) -> None:
        expected = str(cfg.auth_token or "").strip()
        if not expected:
            return
        provided = str(token or "").strip()
        if not provided or not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=401, detail="invalid auth token")

    def _check_image_size(image_b64: str) -> None:
        limit = int(getattr(cfg, "max_image_b64_bytes", 12 * 1024 * 1024))
        if len(str(image_b64 or "")) > limit:
            raise HTTPException(status_code=413, detail=f"image_b64 exceeds limit ({limit} bytes)")

    def _safe_decode(image_b64: str):
        _check_image_size(image_b64)
        try:
            return engine.decode_image(image_b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid image_b64: {exc}")

    def _run_guarded(fn):
        try:
            return fn()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        backends = getattr(engine, "backends", None)
        backend_status = {
            "loaded": bool(getattr(backends, "is_loaded", False)),
            "yolo": bool(getattr(backends, "yolo", None) is not None),
            "face_recognition": bool(getattr(backends, "face_recognition", None) is not None),
            "deepface": bool(getattr(backends, "deepface", None) is not None),
            "advanced_caption": bool(getattr(backends, "caption_pipe", None) is not None),
            "ocr_backend": str(getattr(backends, "ocr_backend_name", "") or ""),
            "known_faces_count": len(getattr(engine, "_known_faces", []) or []),
        }
        return {
            "ok": True,
            "auth_enabled": bool(cfg.auth_token),
            "vram": _vram_summary(),
            "backends": backend_status,
            "qwen": _qwen_health_cached(cfg),
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
        _check_image_size(req.image_b64)
        return _run_guarded(
            lambda: engine.analyze(
                req.image_b64,
                requested_tasks=req.requested_tasks,
                run_semantic_vlm=req.run_semantic_vlm,
                semantic_reason=req.semantic_reason or "",
                request_id=req.request_id or "",
                question=req.question or "",
                task_mode=req.mode or "legacy",
                onsensor_hints=req.onsensor_hints,
            )
        )

    @app.post("/vision/analyze/cheap")
    def analyze_cheap(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        _check_image_size(req.image_b64)
        return _run_guarded(
            lambda: engine.analyze_cheap(
                req.image_b64,
                requested_tasks=req.requested_tasks,
                semantic_reason=req.semantic_reason or "cheap_poll",
                request_id=req.request_id or "",
                question=req.question or "",
                onsensor_hints=req.onsensor_hints,
            )
        )

    @app.post("/vision/analyze/semantic")
    def analyze_semantic(req: AnalyzeRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        _check_image_size(req.image_b64)
        return _run_guarded(
            lambda: engine.analyze_semantic(
                req.image_b64,
                requested_tasks=req.requested_tasks,
                semantic_reason=req.semantic_reason or "semantic_request",
                request_id=req.request_id or "",
                question=req.question or "",
                onsensor_hints=req.onsensor_hints,
            )
        )

    @app.post("/vision/register_face")
    def register_face(req: RegisterFaceRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        name = str(req.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        _check_image_size(req.image_b64)
        return _run_guarded(lambda: engine.register_face(name=name, image_b64=req.image_b64))

    @app.post("/vision/ocr")
    def ocr(req: OcrRequest, x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(x_auth_token)
        frame = _safe_decode(req.image_b64)
        return engine.ocr_frame(frame, languages=req.languages)

    return app


def run_app() -> None:
    import uvicorn

    cfg = load_runtime_config()
    public_bind = str(cfg.host).strip().lower() in {"0.0.0.0", "::", "[::]"}
    if public_bind and not str(cfg.auth_token or "").strip():
        raise RuntimeError(
            "MM_AUTH_TOKEN or SENTRYBOT_VLM_AUTH_TOKEN is required when remote_multimodal binds to a public interface"
        )
    uvicorn.run(create_app(cfg, lazy_backends=True), host=cfg.host, port=cfg.port)
