"""FastAPI router for Speaker ID and Multi-Modal Identity Fusion."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.voiceprint import pcm_b64_to_f32
from ..xSpeakerIdService import SpeakerIdError, SpeakerIdService, get_default


class SignalPayload(BaseModel):
    modality: str = ""
    person_id: str = ""
    name: str = ""
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    ttl_s: Optional[float] = Field(default=None, gt=0.0)
    uid: str = ""


class EnrollPayload(BaseModel):
    name: str = ""
    person_id: str = ""
    samplerate: int = Field(default=16000, gt=0, le=192000)
    replace: bool = False
    pcm: Optional[List[float]] = None
    pcm_b64: Optional[str] = None


class IdentifyPayload(BaseModel):
    samplerate: int = Field(default=16000, gt=0, le=192000)
    pcm: Optional[List[float]] = None
    pcm_b64: Optional[str] = None


def get_router(service: Optional[SpeakerIdService] = None) -> APIRouter:
    router = APIRouter()
    svc = service or get_default()

    def _svc() -> SpeakerIdService:
        nonlocal svc
        if svc is None:
            svc = get_default()
        assert svc is not None
        return svc

    def _status_payload() -> Dict[str, Any]:
        s = _svc()
        data = s.status()
        resolver = getattr(s, "identity_resolver", None)
        if resolver is not None and "identity_fusion" not in data:
            data["identity_fusion"] = resolver.status()
        return data

    def _profiles_payload() -> Dict[str, Any]:
        s = _svc()
        profiles = s.list_profiles() if hasattr(s, "list_profiles") else s.store.names()
        return {"ok": True, "profiles": profiles, "count": len(profiles)}

    def _forget_payload(person_id: str) -> Dict[str, Any]:
        s = _svc()
        try:
            return s.forget(person_id)
        except SpeakerIdError as exc:
            return {"ok": False, "error": str(exc)}

    def _active_identity_payload() -> Dict[str, Any]:
        s = _svc()
        resolved = s.resolve_active_identity()
        return {"ok": True, **resolved}

    def _signal_payload(body: SignalPayload) -> Dict[str, Any]:
        s = _svc()
        res = s.record_identity_signal(
            modality=body.modality.strip().lower(),
            person_id=(body.person_id or body.name).strip(),
            confidence=float(body.confidence),
            ttl_s=float(body.ttl_s) if body.ttl_s is not None else None,
            uid=str(body.uid or ""),
        )
        if res.get("ok") is False:
            return res
        return {"ok": True, **res}

    def _decode_pcm(pcm: Optional[List[float]], pcm_b64: Optional[str]) -> Any:
        if pcm is not None:
            return pcm
        if pcm_b64:
            try:
                return pcm_b64_to_f32(pcm_b64)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail="pcm or pcm_b64 required")

    def _enroll_payload(body: EnrollPayload) -> Dict[str, Any]:
        s = _svc()
        name = (body.name or body.person_id).strip()
        pcm = _decode_pcm(body.pcm, body.pcm_b64)
        try:
            return s.enroll_speaker(name=name, speaker_pcm=pcm, samplerate=body.samplerate, replace=body.replace)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _identify_payload(body: IdentifyPayload) -> Dict[str, Any]:
        s = _svc()
        pcm = _decode_pcm(body.pcm, body.pcm_b64)
        try:
            return s.identify(speaker_pcm=pcm, samplerate=body.samplerate)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Unprefixed routes (when mounted with prefix="/speaker_id") and explicit "/speaker_id/*" routes
    for prefix in ("", "/speaker_id"):
        router.add_api_route(f"{prefix}/status", _status_payload, methods=["GET"])
        router.add_api_route(f"{prefix}/profiles", _profiles_payload, methods=["GET"])
        router.add_api_route(f"{prefix}/profiles/{{person_id}}", _forget_payload, methods=["DELETE"])
        router.add_api_route(f"{prefix}/forget/{{person_id}}", _forget_payload, methods=["DELETE", "POST"])
        router.add_api_route(f"{prefix}/active_identity", _active_identity_payload, methods=["GET"])
        router.add_api_route(f"{prefix}/signal", _signal_payload, methods=["POST"])
        router.add_api_route(f"{prefix}/enroll", _enroll_payload, methods=["POST"])
        router.add_api_route(f"{prefix}/identify", _identify_payload, methods=["POST"])

    return router
