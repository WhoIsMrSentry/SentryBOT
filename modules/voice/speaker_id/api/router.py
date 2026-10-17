from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

from ..xSpeakerIdService import SpeakerIdError, SpeakerIdService, pcm_b64_to_f32


class EnrollReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    pcm_b64: str
    samplerate: int = Field(gt=0)
    replace: bool = False


class IdentifyReq(BaseModel):
    pcm_b64: str
    samplerate: int = Field(gt=0)


class ForgetReq(BaseModel):
    name: str


def get_router(service: Optional[SpeakerIdService] = None) -> APIRouter:
    service = service or SpeakerIdService()
    router = APIRouter(prefix="/speaker_id", tags=["speaker_id"])

    @router.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return service.health()

    @router.get("/status")
    def status() -> Dict[str, Any]:
        return service.status()

    @router.post("/enroll")
    def enroll(req: EnrollReq) -> Dict[str, Any]:
        try:
            pcm = pcm_b64_to_f32(req.pcm_b64)
            return service.enroll_speaker(req.name, pcm, req.samplerate, replace=req.replace)
        except SpeakerIdError as exc:
            return {"ok": False, "error": "speaker_id_error", "detail": str(exc)}

    @router.post("/identify")
    def identify(req: IdentifyReq) -> Dict[str, Any]:
        try:
            pcm = pcm_b64_to_f32(req.pcm_b64)
            return service.identify(pcm, req.samplerate)
        except SpeakerIdError as exc:
            return {"ok": False, "error": "speaker_id_error", "detail": str(exc)}

    @router.post("/forget")
    def forget(req: ForgetReq) -> Dict[str, Any]:
        try:
            return service.forget(req.name)
        except SpeakerIdError as exc:
            return {"ok": False, "error": "speaker_id_error", "detail": str(exc)}

    return router
