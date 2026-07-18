from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..services.capture import CameraCapture

CAMERA_RUNNER_STATUS_COMPATIBILITY_CONTRACT = True


class TrackingSelection(BaseModel):
    label: str = Field(default="person", min_length=1, max_length=80)
    strategy: str = Field(default="largest", min_length=1, max_length=20)
    track_id: Optional[int] = Field(default=None, ge=1)


def get_router(
    capture: CameraCapture,
    fps: int,
    *,
    enabled: bool = True,
    imx500_runner: Optional[Any] = None,
    onsensor_bus: Optional[Any] = None,
) -> APIRouter:
    router = APIRouter()

    def runner_status() -> dict[str, Any]:
        if imx500_runner is None:
            return {"enabled": False, "available": False, "running": False, "reason": "not_configured"}
        try:
            return dict(imx500_runner.status())
        except Exception as exc:
            return {"enabled": True, "available": False, "running": False, "reason": "status_error", "error": str(exc)}

    def bus_status() -> dict[str, Any]:
        if onsensor_bus is None:
            return {"attached": False, "has_latest": False, "published_count": 0}
        stats = dict(onsensor_bus.stats()) if hasattr(onsensor_bus, "stats") else {}
        latest = onsensor_bus.latest() if hasattr(onsensor_bus, "latest") else None
        latest_age = None
        if latest is not None:
            latest_age = max(0.0, time.time() - float(getattr(latest, "ts", 0.0)))
        return {**stats, "attached": True, "has_latest": latest is not None, "latest_age_s": latest_age}

    @router.get("/video")
    async def video_stream():
        if not enabled:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "camera_disabled"})
        return StreamingResponse(
            capture.mjpeg_generator(fps),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-cache"},
        )

    @router.get("/snap")
    async def snapshot():
        if not enabled:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "camera_disabled"})
        data = await capture.snapshot()
        if not data:
            return Response(status_code=503)
        return Response(data, media_type="image/jpeg")

    @router.get("/healthz")
    async def healthz():
        status = capture.status()
        healthy = bool(enabled and status.get("running") and status.get("has_frame") and not status.get("gave_up"))
        return {
            "ok": healthy,
            "enabled": bool(enabled),
            "capture": status,
            "imx500": runner_status(),
        }

    @router.get("/status")
    async def status():
        capture_status = capture.status()
        imx_status = runner_status()
        return {
            "ok": bool(enabled and capture_status.get("running") and capture_status.get("has_frame")),
            "enabled": bool(enabled),
            "capture": capture_status,
            "imx500": imx_status,
            "onsensor": bus_status(),
        }

    @router.get("/onsensor/latest")
    async def onsensor_latest():
        if onsensor_bus is None:
            return {"ok": False, "reason": "onsensor_bus_unavailable"}
        latest = onsensor_bus.latest()
        payload = latest.to_dict() if latest is not None and hasattr(latest, "to_dict") else latest
        return {"ok": latest is not None, "snapshot": payload, "stats": bus_status()}

    @router.get("/tracking/tracks")
    async def tracking_tracks():
        if imx500_runner is None:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "imx500_unavailable"})
        return imx500_runner.tracks()

    @router.get("/tracking/target")
    async def tracking_target():
        if imx500_runner is None:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "imx500_unavailable"})
        return imx500_runner.target()

    @router.post("/tracking/select")
    async def tracking_select(selection: TrackingSelection):
        if imx500_runner is None:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "imx500_unavailable"})
        strategy = selection.strategy.strip().lower()
        if strategy not in {"largest", "center", "confidence"}:
            return JSONResponse(status_code=422, content={"ok": False, "reason": "invalid_strategy"})
        return imx500_runner.select_target(
            label=selection.label,
            strategy=strategy,
            track_id=selection.track_id,
        )

    @router.post("/start")
    async def start_camera():
        if not enabled:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "camera_disabled"})
        capture.start()
        if imx500_runner is not None:
            imx500_runner.attach_camera(capture.picam, capture)
            imx500_runner.start()
        return {"ok": True, "capture": capture.status(), "imx500": runner_status()}

    @router.post("/stop")
    async def stop_camera():
        if imx500_runner is not None:
            imx500_runner.stop()
        capture.stop()
        return {"ok": True}

    return router


__all__ = ["get_router"]
