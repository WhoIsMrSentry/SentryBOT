from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger("camera.service")

# Paket içi importlar, script modunda fallback ile
try:
    from .config_loader import load_config
    from .services.capture import CameraCapture, FramePublisher, CaptureConfig
    from .api import get_router
except Exception:  # when run as script without package context
    from config_loader import load_config  # type: ignore
    from services.capture import CameraCapture, FramePublisher, CaptureConfig  # type: ignore
    from api import get_router  # type: ignore

try:
    # Merkezi loglama (opsiyonel). Başarısız olsa bile modül çalışsın.
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore

    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    enabled = bool(cfg.get("enabled", False))

    cap_cfg = CaptureConfig(
        backend=cfg.get("backend", "auto"),
        source=cfg.get("source", 0),
        resolution=(int(cfg.get("resolution", {}).get("width", 1280)), int(cfg.get("resolution", {}).get("height", 720))),
        fps_target=int(cfg.get("fps_target", 30)),
        jpeg_quality=int(cfg.get("jpeg_quality", 80)),
        opencv_fourcc=str(cfg.get("opencv", {}).get("fourcc", "MJPG")),
        opencv_buffer_size=int(cfg.get("opencv", {}).get("buffer_size", 1)),
        picam_size=(int(cfg.get("picamera2", {}).get("size", {}).get("width", 1920)), int(cfg.get("picamera2", {}).get("size", {}).get("height", 1080))),
        picam_format=str(cfg.get("picamera2", {}).get("format", "RGB888")),
        picam_frame_rate=int(cfg.get("picamera2", {}).get("frame_rate", 30)),
        picam_af_mode=int(cfg.get("picamera2", {}).get("af_mode", 2)),
        flip=str(cfg.get("flip", "none")),
        opencv_max_open_attempts=int(cfg.get("opencv", {}).get("max_open_attempts", 5)),
        opencv_retry_interval_s=float(cfg.get("opencv", {}).get("retry_interval_s", 1.0)),
    )

    publisher = FramePublisher()
    capture = CameraCapture(cap_cfg, publisher)
    if enabled:
        capture.start()
    else:
        logger.info("camera capture disabled (config enabled=false)")

    app = FastAPI()
    app.include_router(get_router(capture, cap_cfg.fps_target, enabled=enabled))
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg.get("server", {}).get("host", "0.0.0.0")),
        port=int(cfg.get("server", {}).get("port", 8000)),
    )
