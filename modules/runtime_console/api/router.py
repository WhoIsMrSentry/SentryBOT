from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, HTTPException, Query, Request

from ..event_bus import get_event_bus

router = APIRouter(prefix="/runtime_console", tags=["runtime_console"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _configured_auth_token() -> str:
    for env_name in (
        "SENTRYBOT_RUNTIME_CONSOLE_TOKEN",
        "SENTRYBOT_GATEWAY_API_KEY",
        "SENTRYBOT_AGENT_AUTH_TOKEN",
    ):
        val = str(os.getenv(env_name, "")).strip()
        if val and val.lower() != "changeme":
            return val
    return ""


def _authorize_events_request(request: Request) -> None:
    expected = _configured_auth_token()
    if expected:
        auth_hdr = str(request.headers.get("Authorization") or "").strip()
        bearer = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else ""
        provided = (
            str(request.headers.get("X-Auth-Token") or "").strip()
            or str(request.headers.get("X-API-Key") or "").strip()
            or bearer
        )
        if not provided or not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
        return

    client_host = request.client.host if request.client else ""
    if client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="Remote access to runtime console events requires token authentication",
        )


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "events": len(list(get_event_bus().iter()))}


@router.get("/events")
def events(request: Request, limit: int = Query(default=20, ge=1, le=200)) -> dict:
    _authorize_events_request(request)
    return {"ok": True, "events": [event.__dict__ for event in get_event_bus().tail(limit)]}
