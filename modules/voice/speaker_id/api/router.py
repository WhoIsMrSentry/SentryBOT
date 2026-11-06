"""FastAPI router for Speaker ID and Multi-Modal Identity Fusion."""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body

from ..xSpeakerIdService import SpeakerIdError, SpeakerIdService, get_default


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

    def _signal_payload(body: Dict[str, Any]) -> Dict[str, Any]:
        s = _svc()
        modality = str(body.get("modality") or "").strip().lower()
        person_id = str(body.get("person_id") or body.get("name") or "").strip()
        confidence = float(body.get("confidence", 0.75))
        ttl_s = body.get("ttl_s")
        uid = str(body.get("uid") or "")
        res = s.record_identity_signal(
            modality=modality,
            person_id=person_id,
            confidence=confidence,
            ttl_s=float(ttl_s) if ttl_s is not None else None,
            uid=uid,
        )
        if res.get("ok") is False:
            return res
        return {"ok": True, **res}

    def _enroll_payload(body: Dict[str, Any]) -> Dict[str, Any]:
        s = _svc()
        name = str(body.get("name") or body.get("person_id") or "").strip()
        samplerate = int(body.get("samplerate", 16000))
        replace = bool(body.get("replace", False))
        pcm = body.get("pcm")
        if pcm is None and body.get("pcm_b64"):
            pcm = base64.b64decode(str(body["pcm_b64"]))
        try:
            return s.enroll_speaker(name=name, speaker_pcm=pcm, samplerate=samplerate, replace=replace)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _identify_payload(body: Dict[str, Any]) -> Dict[str, Any]:
        s = _svc()
        samplerate = int(body.get("samplerate", 16000))
        pcm = body.get("pcm")
        if pcm is None and body.get("pcm_b64"):
            pcm = base64.b64decode(str(body["pcm_b64"]))
        try:
            return s.identify(speaker_pcm=pcm, samplerate=samplerate)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Unprefixed routes (when mounted with prefix="/speaker_id") and explicit "/speaker_id/*" routes
    for prefix in ("", "/speaker_id"):
        router.add_api_route(f"{prefix}/status", _status_payload, methods=["GET"])
        router.add_api_route(f"{prefix}/profiles", _profiles_payload, methods=["GET"])
        router.add_api_route(f"{prefix}/profiles/{{person_id}}", _forget_payload, methods=["DELETE"])
        router.add_api_route(f"{prefix}/forget/{{person_id}}", _forget_payload, methods=["DELETE", "POST"])
        router.add_api_route(f"{prefix}/active_identity", _active_identity_payload, methods=["GET"])
        router.add_api_route(
            f"{prefix}/signal",
            lambda body=Body(default={}): _signal_payload(body if isinstance(body, dict) else {}),
            methods=["POST"],
        )
        router.add_api_route(
            f"{prefix}/enroll",
            lambda body=Body(default={}): _enroll_payload(body if isinstance(body, dict) else {}),
            methods=["POST"],
        )
        router.add_api_route(
            f"{prefix}/identify",
            lambda body=Body(default={}): _identify_payload(body if isinstance(body, dict) else {}),
            methods=["POST"],
        )

    return router
