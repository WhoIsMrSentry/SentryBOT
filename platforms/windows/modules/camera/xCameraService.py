from __future__ import annotations
from fastapi import FastAPI

# Windows override: force OpenCV backend and DirectShow device index
try:
    from .config_loader import load_config
    from .services.capture import CameraCapture, FramePublisher, CaptureConfig
    from .api import get_router
except Exception:  # when run as script
    from config_loader import load_config  # type: ignore
    from services.capture import CameraCapture, FramePublisher, CaptureConfig  # type: ignore
    from api import get_router  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    # Enforce Windows-friendly defaults
    cfg["backend"] = "opencv"
    # Prefer MJPG and small buffer to reduce latency on webcams
    cfg.setdefault("opencv", {})
    cfg["opencv"].setdefault("fourcc", "MJPG")
    cfg["opencv"].setdefault("buffer_size", 1)

    cap_cfg = CaptureConfig(
        backend="opencv",
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
    )

    publisher = FramePublisher()
    capture = CameraCapture(cap_cfg, publisher)
    capture.start()

    app = FastAPI()
    app.include_router(get_router(capture, cap_cfg.fps_target))
    return app
