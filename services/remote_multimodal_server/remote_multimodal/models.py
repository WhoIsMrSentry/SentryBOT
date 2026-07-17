from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    image_b64: str
    requested_tasks: Optional[List[str]] = None
    # Explicit semantic budget controls. When omitted, the server keeps
    # legacy behavior for older clients. New SentryBOT clients always set
    # run_semantic_vlm so cheap object/person polling does not wake Qwen.
    run_semantic_vlm: Optional[bool] = None
    semantic_reason: Optional[str] = None
    request_id: Optional[str] = None
    question: Optional[str] = None
    # Optional client-visible task mode: cheap | semantic | legacy.
    mode: Optional[str] = None


class RegisterFaceRequest(BaseModel):
    name: str
    image_b64: str


class OcrRequest(BaseModel):
    image_b64: str
    languages: Optional[List[str]] = None


@dataclass
class KnownFace:
    name: str
    embedding: List[float]
    created_at: float = field(default_factory=time.time)


def known_face_to_dict(face: KnownFace) -> Dict[str, Any]:
    return {
        "name": face.name,
        "embedding": list(face.embedding),
        "created_at": float(face.created_at),
    }


def known_face_from_dict(data: Dict[str, Any]) -> Optional[KnownFace]:
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    emb = data.get("embedding")
    if not name or not isinstance(emb, list) or not emb:
        return None
    try:
        vec = [float(v) for v in emb]
    except Exception:
        return None
    created_at = float(data.get("created_at", time.time()))
    return KnownFace(name=name, embedding=vec, created_at=created_at)
