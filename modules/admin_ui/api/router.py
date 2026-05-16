"""FastAPI router that exposes the Admin UI surface.

Endpoints:

- ``GET /admin/ui`` and ``GET /admin/ui/{path:path}`` — serve the vanilla HTML
  bundle from :mod:`modules.admin_ui.static`.
- ``GET /admin/api/status`` — aggregated dashboard snapshot.
- ``GET /admin/api/vision`` — vision pipeline state.
- ``GET /admin/api/people`` — social database people view.
- ``GET /admin/api/profiles`` — realtime / subagent profile state.
- ``GET /admin/api/config`` — runtime registry keys.
- ``GET /admin/api/hardware`` — hardware presence map.
- ``POST /admin/api/profile/switch`` — atomically switch realtime profile.
- ``GET /admin/api/stream`` — SSE feed (status snapshots).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..services.dashboard import DashboardAggregator
from ..services.lan_filter import is_allowed_client

logger = logging.getLogger("admin_ui.api")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _require_lan(request: Request, cfg: Dict[str, Any]) -> None:
    enforce = bool(cfg.get("bind_lan_only", True))
    networks = cfg.get("allowed_networks") or []
    remote_host = request.client.host if request.client else ""
    xff = request.headers.get("X-Forwarded-For")
    if not is_allowed_client(remote_host, xff, networks, enforce):
        raise HTTPException(status_code=403, detail="admin_ui: client outside LAN allowlist")


def _require_token(cfg: Dict[str, Any], provided: Optional[str]) -> None:
    auth_cfg = cfg.get("auth", {}) if isinstance(cfg.get("auth", {}), dict) else {}
    token = str(auth_cfg.get("token", "") or "").strip()
    if not token:
        return
    if provided != token:
        raise HTTPException(status_code=401, detail="admin_ui: invalid admin token")


def get_router(cfg: Dict[str, Any], aggregator: DashboardAggregator, started: Dict[str, Any]) -> APIRouter:
    router = APIRouter(prefix=str(cfg.get("mount_prefix", "/admin") or "/admin"), tags=["admin_ui"])
    auth_header = str(cfg.get("auth", {}).get("header", "X-Admin-Token") or "X-Admin-Token")

    def _gate(request: Request, token: Optional[str]) -> None:
        _require_lan(request, cfg)
        _require_token(cfg, token)

    @router.get("/health", summary="Admin UI health")
    def health(request: Request) -> Dict[str, Any]:
        _require_lan(request, cfg)
        return {
            "ok": True,
            "ts": time.time(),
            "lan_only": bool(cfg.get("bind_lan_only", True)),
            "auth_required": bool(cfg.get("auth", {}).get("token")),
            "mount_prefix": cfg.get("mount_prefix", "/admin"),
        }

    @router.get("/ui", summary="Serve admin dashboard")
    def ui_index(request: Request) -> Response:
        _require_lan(request, cfg)
        index = _STATIC_DIR / "index.html"
        if not index.exists():
            return HTMLResponse("<h1>Admin UI assets missing</h1>", status_code=500)
        return FileResponse(str(index))

    @router.get("/ui/{path:path}", summary="Serve admin dashboard asset")
    def ui_asset(path: str, request: Request) -> Response:
        _require_lan(request, cfg)
        candidate = (_STATIC_DIR / path).resolve()
        try:
            candidate.relative_to(_STATIC_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="asset not found")
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(str(candidate))

    @router.get("/api/status", summary="Aggregated status snapshot")
    def api_status(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.status_snapshot()

    @router.get("/api/vision", summary="Vision pipeline snapshot")
    def api_vision(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.vision_snapshot()

    @router.get("/api/people", summary="Social DB people snapshot")
    def api_people(request: Request, limit: int = 50, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.people_snapshot(limit=max(1, min(500, int(limit))))

    @router.get("/api/profiles", summary="Realtime profile + subagent snapshot")
    def api_profiles(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.profiles_snapshot()

    @router.get("/api/config", summary="Runtime registry snapshot")
    def api_config(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.config_snapshot()

    @router.get("/api/hardware", summary="Hardware presence snapshot")
    def api_hardware(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.hardware_snapshot()

    @router.get("/api/all", summary="All snapshots in a single payload")
    def api_all(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> Dict[str, Any]:
        _gate(request, token)
        return aggregator.all_snapshots()

    @router.post("/api/profile/switch", summary="Atomically switch realtime profile")
    def api_profile_switch(
        request: Request,
        body: Dict[str, Any],
        token: Optional[str] = Header(default=None, alias=auth_header),
    ) -> Dict[str, Any]:
        _gate(request, token)
        mode = str((body or {}).get("name") or (body or {}).get("mode") or "").strip().lower()
        if not mode:
            raise HTTPException(status_code=400, detail="name required")
        autonomy = started.get("autonomy")
        agent = started.get("agent_core")
        if agent is None:
            agent = getattr(getattr(autonomy, "brain", None), "agent", None)
        vlm = started.get("vlm_bridge")
        applied: Dict[str, Any] = {}

        profile = None
        rt_cfg_source: Dict[str, Any] = {}
        if agent is not None and hasattr(agent, "config"):
            cfg_src = getattr(agent, "config", {})
            rt_cfg_src = cfg_src.get("realtime_profile", {}) if isinstance(cfg_src, dict) else {}
            if isinstance(rt_cfg_src, dict):
                rt_cfg_source = rt_cfg_src
                profiles_map = rt_cfg_src.get("profiles", {}) if isinstance(rt_cfg_src.get("profiles", {}), dict) else {}
                profile = profiles_map.get(mode)
                if not isinstance(profile, dict) or not profile:
                    cand = rt_cfg_src.get(mode)
                    profile = cand if isinstance(cand, dict) else None

        if isinstance(profile, dict) and agent is not None and hasattr(agent, "apply_realtime_profile"):
            applied["agent_core"] = agent.apply_realtime_profile(profile)
            if isinstance(rt_cfg_source, dict):
                rt_cfg_source["active"] = mode

        if vlm is not None and hasattr(vlm, "apply_realtime_profile"):
            applied["vlm_bridge"] = vlm.apply_realtime_profile(mode)

        base_url = str(started.get("gateway_base_url", "http://127.0.0.1:8080")).rstrip("/")
        ollama_np = None
        if isinstance(profile, dict):
            ollama_np = profile.get("ollama_num_predict") or profile.get("num_predict")

        if ollama_np is not None:
            try:
                import requests  # type: ignore

                r_ol = requests.post(
                    f"{base_url}/ollama/runtime/num_predict",
                    json={"num_predict": int(ollama_np)},
                    timeout=2.0,
                )
                applied["ollama"] = {"ok": r_ol.status_code == 200, "status": r_ol.status_code}
            except Exception as exc:
                applied["ollama"] = {"ok": False, "error": str(exc)}

        speak_chunk = None
        if isinstance(profile, dict):
            speak_chunk = profile.get("speak_max_chunk_chars") or profile.get("tts_max_chunk_chars")

        if speak_chunk is not None:
            applied["speak"] = {
                "hint": "Speak service uses /speak/say_stream max_chunk_chars per call; hot field not wired yet.",
                "max_chunk_chars": int(speak_chunk),
            }

        return {"ok": True, "profile": mode, "applied": applied}

    @router.get("/api/stream", summary="SSE stream of dashboard snapshots")
    async def api_stream(request: Request, token: Optional[str] = Header(default=None, alias=auth_header)) -> StreamingResponse:
        _gate(request, token)
        interval = max(0.25, float(cfg.get("sse", {}).get("interval_s", 1.0)))
        heartbeat = max(interval, float(cfg.get("sse", {}).get("heartbeat_s", 10.0)))

        async def _gen():
            last_beat = time.time()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = aggregator.status_snapshot()
                    yield f"event: status\ndata: {json.dumps(payload, default=str)}\n\n"
                except Exception as exc:
                    logger.debug("admin sse status failure: %s", exc)
                if (time.time() - last_beat) >= heartbeat:
                    yield ": keep-alive\n\n"
                    last_beat = time.time()
                await asyncio.sleep(interval)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    return router


def mount(app: FastAPI, cfg: Dict[str, Any], started: Dict[str, Any]) -> APIRouter:
    aggregator = DashboardAggregator(started)
    router = get_router(cfg, aggregator, started)
    app.include_router(router)
    return router
