from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

def load_dotenv_once() -> None:
    candidates = [Path.cwd() / ".env"]
    try:
        candidates.append(Path(__file__).resolve().parents[3] / ".env")
    except Exception:
        pass
    for target in candidates:
        if not target.exists():
            continue
        for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('\"').strip("'")


def ollama_chat_endpoint_default() -> str:
    raw = (
        os.getenv("MM_QWEN_ENDPOINT")
        or os.getenv("OLLAMA_CHAT_ENDPOINT")
        or os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST")
        or "http://whoismrsentry.local:11434"
    )
    value = str(raw).strip().rstrip("/")
    if value.endswith("/api/chat"):
        return value
    if value.endswith("/api/tags"):
        return value[:-9] + "/api/chat"
    return value + "/api/chat"



class RuntimeConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8091
    auth_token: str = ""
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
    qwen_endpoint: str = "http://whoismrsentry.local:11434/api/chat"
    qwen_primary_model: str = "qwen3.5:9b"
    qwen_fallback_model: str = "qwen3.5:9b"
    qwen_timeout_s: float = 8.0
    qwen_num_predict: int = 192
    qwen_num_ctx: int = 2048
    qwen_temperature: float = 0.1
    enable_advanced_caption: bool = False
    advanced_caption_model: str = "microsoft/Florence-2-base"
    enable_ocr: bool = True
    ocr_backend: str = "auto"  # auto | paddleocr | easyocr | tesseract
    ocr_languages: str = "en,tr"
    ocr_min_confidence: float = 0.4


def load_runtime_config() -> RuntimeConfig:
    load_dotenv_once()
    base_dir = Path(__file__).resolve().parent.parent
    return RuntimeConfig(
        host=str(os.getenv("MM_HOST", os.getenv("SENTRYBOT_MM_HOST", "127.0.0.1"))).strip() or "127.0.0.1",
        port=int(os.getenv("MM_PORT", "8091")),
        auth_token=str(os.getenv("MM_AUTH_TOKEN", os.getenv("SENTRYBOT_VLM_AUTH_TOKEN", ""))).strip(),
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
        qwen_endpoint=ollama_chat_endpoint_default(),
        qwen_primary_model=str(os.getenv("MM_QWEN_PRIMARY_MODEL", "qwen3.5:9b")).strip()
        or "qwen3.5:9b",
        qwen_fallback_model=str(os.getenv("MM_QWEN_FALLBACK_MODEL", "qwen3.5:9b")).strip()
        or "qwen3.5:9b",
        qwen_timeout_s=float(os.getenv("MM_QWEN_TIMEOUT", "8.0")),
        qwen_num_predict=int(os.getenv("MM_QWEN_NUM_PREDICT", "192")),
        qwen_num_ctx=int(os.getenv("MM_QWEN_NUM_CTX", "2048")),
        qwen_temperature=float(os.getenv("MM_QWEN_TEMPERATURE", "0.1")),
        enable_advanced_caption=bool_env("MM_ENABLE_ADVANCED_CAPTION", False),
        advanced_caption_model=str(
            os.getenv("MM_ADVANCED_CAPTION_MODEL", "microsoft/Florence-2-base")
        ).strip(),
        enable_ocr=bool_env("MM_ENABLE_OCR", True),
        ocr_backend=str(os.getenv("MM_OCR_BACKEND", "auto")).strip().lower() or "auto",
        ocr_languages=str(os.getenv("MM_OCR_LANGUAGES", "en,tr")).strip() or "en,tr",
        ocr_min_confidence=float(os.getenv("MM_OCR_MIN_CONFIDENCE", "0.4")),
    )
