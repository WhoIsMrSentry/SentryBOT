from __future__ import annotations

import logging

from fastapi import FastAPI

from .api import get_router
from .config_loader import load_config
from .services.capture import CameraCapture, CaptureConfig, FramePublisher
from .services.imx500_runner import Imx500Config, Imx500Runner
from .services.onsensor_bus import get_default_bus

logger = logging.getLogger("camera.service")


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    enabled = bool(cfg.get("enabled", True))
    picam_cfg = cfg.get("picamera2", {}) if isinstance(cfg.get("picamera2"), dict) else {}
    size_cfg = picam_cfg.get("size", {}) if isinstance(picam_cfg.get("size"), dict) else {}
    imx_raw = cfg.get("imx500", {}) if isinstance(cfg.get("imx500"), dict) else {}
    tracker_raw = imx_raw.get("tracker", {}) if isinstance(imx_raw.get("tracker"), dict) else {}
    target_raw = imx_raw.get("target", {}) if isinstance(imx_raw.get("target"), dict) else {}

    bus = get_default_bus()
    runner = Imx500Runner(
        Imx500Config(
            enabled=bool(imx_raw.get("enabled", True)),
            model_path=str(imx_raw.get("model_path", Imx500Config.model_path)),
            labels_path=str(imx_raw.get("labels_path", "")),
            confidence=float(imx_raw.get("confidence", 0.50)),
            iou=float(imx_raw.get("iou", 0.65)),
            max_detections=int(imx_raw.get("max_detections", 20)),
            publish_interval_s=float(imx_raw.get("publish_interval_s", 0.05)),
            inference_rate=int(imx_raw["inference_rate"]) if imx_raw.get("inference_rate") is not None else None,
            preserve_aspect_ratio=bool(imx_raw.get("preserve_aspect_ratio", True)),
            classes_of_interest=tuple(imx_raw.get("classes_of_interest", []) or []),
            tracker_iou_threshold=float(tracker_raw.get("iou_threshold", 0.30)),
            tracker_max_missed=int(tracker_raw.get("max_missed", 8)),
            target_label=str(target_raw.get("label", "person")),
            target_strategy=str(target_raw.get("strategy", "largest")),
        ),
        bus=bus,
    )
    runner.prepare()
    capture = CameraCapture(
        CaptureConfig(
            size=(int(size_cfg.get("width", 1280)), int(size_cfg.get("height", 720))),
            pixel_format=str(picam_cfg.get("format", "RGB888")),
            frame_rate=int(picam_cfg.get("frame_rate", cfg.get("fps_target", 30))),
            jpeg_quality=int(cfg.get("jpeg_quality", 80)),
            flip=str(cfg.get("flip", "none")),
            camera_num=runner.camera_num,
        ),
        FramePublisher(),
    )
    if enabled:
        capture.start()
        runner.attach_camera(capture.picam, capture)
        runner.start()
    else:
        logger.info("camera disabled")

    app = FastAPI()
    app.include_router(
        get_router(
            capture,
            int(cfg.get("fps_target", 30)),
            enabled=enabled,
            imx500_runner=runner,
            onsensor_bus=bus,
        )
    )
    return app


if __name__ == "__main__":
    import uvicorn

    configuration = load_config()
    uvicorn.run(
        create_app(),
        host=str(configuration.get("server", {}).get("host", "0.0.0.0")),
        port=int(configuration.get("server", {}).get("port", 8000)),
    )
