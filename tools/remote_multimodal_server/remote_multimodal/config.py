from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class RuntimeConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8091
    auth_token: str = "changeme"
    face_db_path: str = "known_faces.json"
    yolo_model: str = "yolov8n.pt"
    detector_backend: str = "auto"  # auto | yolo | opencv
    runtime_profile: str = "balanced"  # ultra_fast | balanced | max_accuracy
    yolo_conf: float = 0.25
    yolo_imgsz: int = 640
    motion_threshold: float = 0.08
    scene_change_threshold: float = 0.35
    enable_face_recognition: bool = True
    enable_age_emotion: bool = True
    enable_qwen_vlm: bool = True
    qwen_endpoint: str = "http://127.0.0.1:11434/api/chat"
    qwen_primary_model: str = "qwen2.5vl:7b"
    qwen_fallback_model: str = "qwen3-vl:8b"
    qwen_timeout_s: float = 8.0
    qwen_num_predict: int = 192
    qwen_num_ctx: int = 2048
    qwen_temperature: float = 0.1
    enable_advanced_caption: bool = False
    advanced_caption_model: str = "microsoft/Florence-2-base"


def load_runtime_config() -> RuntimeConfig:
    base_dir = Path(__file__).resolve().parent.parent
    return RuntimeConfig(
        host=str(os.getenv("MM_HOST", "0.0.0.0")).strip() or "0.0.0.0",
        port=int(os.getenv("MM_PORT", "8091")),
        auth_token=str(os.getenv("MM_AUTH_TOKEN", "changeme")).strip() or "changeme",
        face_db_path=str(os.getenv("MM_FACE_DB", str(base_dir / "known_faces.json"))).strip(),
        yolo_model=str(os.getenv("MM_YOLO_MODEL", "yolov8n.pt")).strip() or "yolov8n.pt",
        detector_backend=str(os.getenv("MM_DETECTOR_BACKEND", "auto")).strip().lower() or "auto",
        runtime_profile=str(os.getenv("MM_RUNTIME_PROFILE", "balanced")).strip().lower() or "balanced",
        yolo_conf=float(os.getenv("MM_YOLO_CONF", "0.25")),
        yolo_imgsz=int(os.getenv("MM_YOLO_IMGSZ", "640")),
        motion_threshold=float(os.getenv("MM_MOTION_THRESHOLD", "0.08")),
        scene_change_threshold=float(os.getenv("MM_SCENE_CHANGE_THRESHOLD", "0.35")),
        enable_face_recognition=bool_env("MM_ENABLE_FACE_RECOGNITION", True),
        enable_age_emotion=bool_env("MM_ENABLE_AGE_EMOTION", True),
        enable_qwen_vlm=bool_env("MM_ENABLE_QWEN_VLM", True),
        qwen_endpoint=str(
            os.getenv("MM_QWEN_ENDPOINT", "http://127.0.0.1:11434/api/chat")
        ).strip()
        or "http://127.0.0.1:11434/api/chat",
        qwen_primary_model=str(os.getenv("MM_QWEN_PRIMARY_MODEL", "qwen2.5vl:7b")).strip()
        or "qwen2.5vl:7b",
        qwen_fallback_model=str(os.getenv("MM_QWEN_FALLBACK_MODEL", "qwen3-vl:8b")).strip()
        or "qwen3-vl:8b",
        qwen_timeout_s=float(os.getenv("MM_QWEN_TIMEOUT", "8.0")),
        qwen_num_predict=int(os.getenv("MM_QWEN_NUM_PREDICT", "192")),
        qwen_num_ctx=int(os.getenv("MM_QWEN_NUM_CTX", "2048")),
        qwen_temperature=float(os.getenv("MM_QWEN_TEMPERATURE", "0.1")),
        enable_advanced_caption=bool_env("MM_ENABLE_ADVANCED_CAPTION", False),
        advanced_caption_model=str(
            os.getenv("MM_ADVANCED_CAPTION_MODEL", "microsoft/Florence-2-base")
        ).strip(),
    )
