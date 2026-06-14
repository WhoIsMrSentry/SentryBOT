from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, StreamingResponse

try:
    from ..services.capture import CameraCapture
except Exception:  # fallback when run as script
    from services.capture import CameraCapture  # type: ignore


def get_router(capture: CameraCapture, fps: int, *, enabled: bool = True) -> APIRouter:
    router = APIRouter()

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
        if not enabled:
            return {"ok": False, "gave_up": False, "enabled": False, "reason": "camera_disabled"}
        data = await capture.snapshot()
        return {"ok": bool(data), "gave_up": capture.gave_up, "enabled": True}

    @router.post("/start")
    async def start_camera():
        if not enabled:
            return JSONResponse(status_code=503, content={"ok": False, "reason": "camera_disabled"})
        capture.start()
        return {"ok": True}

    @router.post("/stop")
    async def stop_camera():
        capture.stop()
        return {"ok": True}

    return router
