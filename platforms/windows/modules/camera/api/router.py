from __future__ import annotations
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

try:
    from ..services.capture import CameraCapture
except Exception:
    from services.capture import CameraCapture  # type: ignore


essential_headers = {"Cache-Control": "no-cache"}


def get_router(capture: CameraCapture, fps: int) -> APIRouter:
    router = APIRouter()

    @router.get("/video")
    async def video_stream():
        return StreamingResponse(
            capture.mjpeg_generator(fps),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers=essential_headers,
        )

    @router.get("/snap")
    async def snapshot():
        data = await capture.snapshot()
        if not data:
            return Response(status_code=503)
        return Response(data, media_type="image/jpeg")

    @router.get("/healthz")
    async def healthz():
        data = await capture.snapshot()
        return {"ok": bool(data)}

    return router
