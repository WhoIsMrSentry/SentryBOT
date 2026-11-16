from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Set

from pydantic import BaseModel, Field


_PROFILE_DEFAULTS: Dict[str, Dict[str, object]] = {
    "ultra_fast": {
        "yolo_conf": 0.35,
        "yolo_imgsz": 416,
        "motion_threshold": 0.1,
        "scene_change_threshold": 0.4,
        "enable_age_emotion": False,
        "enable_advanced_caption": False,
        "qwen_num_predict": 120,
        "qwen_timeout_s": 5.0,
    },
    "max_accuracy": {
        "yolo_conf": 0.2,
        "yolo_imgsz": 960,
        "motion_threshold": 0.06,
        "scene_change_threshold": 0.3,
        "qwen_num_predict": 256,
        "qwen_timeout_s": 10.0,
    },
    "balanced": {
        "yolo_conf": 0.25,
        "yolo_imgsz": 640,
        "motion_threshold": 0.08,
        "scene_change_threshold": 0.35,
        "qwen_num_predict": 192,
        "qwen_timeout_s": 8.0,
    },
}


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
    max_image_b64_bytes: int = 12 * 1024 * 1024
    max_concurrent_inferences: int = 2
    env_overrides: Set[str] = Field(default_factory=set)


def load_runtime_config() -> RuntimeConfig:
    load_dotenv_once()
    base_dir = Path(__file__).resolve().parent.parent
    profile = str(os.getenv("MM_RUNTIME_PROFILE", "balanced")).strip().lower() or "balanced"
    defaults = _PROFILE_DEFAULTS.get(profile, _PROFILE_DEFAULTS["balanced"])
    env_overrides: Set[str] = set()

    def _fenv(env_key: str, field_name: str) -> float:
        raw = os.getenv(env_key)
        if raw is not None and raw.strip() != "":
            env_overrides.add(field_name)
            return float(raw)
        return float(defaults[field_name])

    def _ienv(env_key: str, field_name: str) -> int:
        raw = os.getenv(env_key)
        if raw is not None and raw.strip() != "":
            env_overrides.add(field_name)
            return int(raw)
        return int(defaults[field_name])

    def _benv(env_key: str, field_name: str, fallback: bool) -> bool:
        if os.getenv(env_key) is not None:
            env_overrides.add(field_name)
            return bool_env(env_key, fallback)
        return bool(defaults.get(field_name, fallback))

    return RuntimeConfig(
        host=str(os.getenv("MM_HOST", os.getenv("SENTRYBOT_MM_HOST", "127.0.0.1"))).strip() or "127.0.0.1",
        port=int(os.getenv("MM_PORT", "8091")),
        auth_token=str(os.getenv("MM_AUTH_TOKEN", os.getenv("SENTRYBOT_VLM_AUTH_TOKEN", ""))).strip(),
        face_db_path=str(os.getenv("MM_FACE_DB", str(base_dir / "known_faces.json"))).strip(),
        yolo_model=str(os.getenv("MM_YOLO_MODEL", "yolov8n.pt")).strip() or "yolov8n.pt",
        detector_backend=str(os.getenv("MM_DETECTOR_BACKEND", "auto")).strip().lower() or "auto",
        runtime_profile=profile,
        yolo_conf=_fenv("MM_YOLO_CONF", "yolo_conf"),
        yolo_imgsz=_ienv("MM_YOLO_IMGSZ", "yolo_imgsz"),
        motion_threshold=_fenv("MM_MOTION_THRESHOLD", "motion_threshold"),
        scene_change_threshold=_fenv("MM_SCENE_CHANGE_THRESHOLD", "scene_change_threshold"),
        enable_face_recognition=bool_env("MM_ENABLE_FACE_RECOGNITION", True),
        enable_age_emotion=_benv("MM_ENABLE_AGE_EMOTION", "enable_age_emotion", True),
        enable_qwen_vlm=bool_env("MM_ENABLE_QWEN_VLM", True),
        qwen_endpoint=ollama_chat_endpoint_default(),
        qwen_primary_model=str(os.getenv("MM_QWEN_PRIMARY_MODEL", "qwen3.5:9b")).strip()
        or "qwen3.5:9b",
        qwen_fallback_model=str(os.getenv("MM_QWEN_FALLBACK_MODEL", "qwen3.5:9b")).strip()
        or "qwen3.5:9b",
        qwen_timeout_s=_fenv("MM_QWEN_TIMEOUT", "qwen_timeout_s"),
        qwen_num_predict=_ienv("MM_QWEN_NUM_PREDICT", "qwen_num_predict"),
        qwen_num_ctx=int(os.getenv("MM_QWEN_NUM_CTX", "2048")),
        qwen_temperature=float(os.getenv("MM_QWEN_TEMPERATURE", "0.1")),
        enable_advanced_caption=_benv("MM_ENABLE_ADVANCED_CAPTION", "enable_advanced_caption", False),
        advanced_caption_model=str(
            os.getenv("MM_ADVANCED_CAPTION_MODEL", "microsoft/Florence-2-base")
        ).strip(),
        enable_ocr=bool_env("MM_ENABLE_OCR", True),
        ocr_backend=str(os.getenv("MM_OCR_BACKEND", "auto")).strip().lower() or "auto",
        ocr_languages=str(os.getenv("MM_OCR_LANGUAGES", "en,tr")).strip() or "en,tr",
        ocr_min_confidence=float(os.getenv("MM_OCR_MIN_CONFIDENCE", "0.4")),
        max_image_b64_bytes=int(os.getenv("MM_MAX_IMAGE_B64_BYTES", str(12 * 1024 * 1024))),
        max_concurrent_inferences=max(1, int(os.getenv("MM_MAX_CONCURRENT_INFERENCES", "2"))),
        env_overrides=env_overrides,
    )
