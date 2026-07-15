from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class PiperVoice:
    voice_id: str
    language: str
    quality: Optional[str]
    model_path: str
    config_path: Optional[str]


@dataclass(frozen=True)
class XttsSourceVoice:
    voice_id: str
    file_path: str
    extension: str


class SynthesizeRequest(BaseModel):
    text: str
    engine: Literal["piper", "xtts"]
    language: Optional[str] = None
    speaker_wav: Optional[str] = None
    piper: Dict[str, Any] = Field(default_factory=dict)
    xtts: Dict[str, Any] = Field(default_factory=dict)
    response_format: Literal["wav", "json_base64"] = "wav"
