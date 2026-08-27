from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI

from .bootstrap_config import (
    _agent_section,
    _merge_with_agent_section,
    _should_autostart_services,
)

logger = logging.getLogger("gateway.bootstrap.hardware")


def _include_arduino(app: FastAPI, started: Dict[str, object], head_arbiter: Optional[Any] = None) -> None:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.api.router import get_router as get_arduino_router  # type: ignore

    ardu = xArduinoSerialService(
        config_overrides=_agent_section("arduino_serial") or None,
        head_arbiter=head_arbiter,
    )
    # Register as the process-wide shared instance so implicit ArduinoDriver()
    # users (piservo ears, tools) reuse THIS service instead of spawning
    # duplicate serial/ESP connections with their own heartbeats (R11/R33).
    try:
        from modules.arduino_serial.services.driver import set_shared_service
        set_shared_service(ardu)
    except Exception:
        pass
    if _should_autostart_services():
        try:
            ardu.start()
        except Exception as exc:
            logger.warning("arduino service failed to start, running degraded: %s", exc)
    else:
        logger.info("arduino auto-start skipped (autostart disabled)")

    started["arduino"] = ardu
    try:
        app.include_router(get_arduino_router(ardu))
    except Exception:
        pass
    logger.info("module arduino mounted")


def _include_esp_link(app: FastAPI, started: Dict[str, object]) -> None:
    """Mount ESP bridge compatibility routes.

    The current ESP HTTP transport lives inside ``xArduinoSerialService`` via
    ``EspTransportMixin``. Older gateway config still has ``include.esp_link``
    and status code still probes ``/esp/healthz``. Keep those routes mounted
    without importing a removed standalone esp_link service.
    """
    import time

    from fastapi import APIRouter, HTTPException

    svc = started.get("arduino")
    router = APIRouter(prefix="/esp", tags=["esp_link"])

    def _state() -> Dict[str, Any]:
        if svc is None:
            return {
                "ok": False,
                "enabled": False,
                "mode": "missing_arduino_service",
                "error": "arduino service is not mounted",
            }
        transport_mode = str(getattr(svc, "_transport_mode", "unknown") or "unknown")
        esp_mode = bool(getattr(svc, "_esp_mode", False))
        paused_until = float(getattr(svc, "_esp_paused_until", 0.0) or 0.0)
        pause_remaining = max(0.0, paused_until - time.time())
        return {
            "ok": bool(pause_remaining <= 0.0),
            "enabled": esp_mode,
            "transport_mode": transport_mode,
            "base_url": str(getattr(svc, "_esp_base_url", "") or ""),
            "request_path": str(getattr(svc, "_esp_request_path", "/request") or "/request"),
            "send_path": str(getattr(svc, "_esp_send_path", "/send") or "/send"),
            "health_path": str(getattr(svc, "_esp_health_path", "/healthz") or "/healthz"),
            "paused": bool(pause_remaining > 0.0),
            "pause_remaining_s": round(pause_remaining, 3),
            "fail_streak": int(getattr(svc, "_esp_fail_streak", 0) or 0),
            "note": "ESP HTTP transport is active" if esp_mode else "Arduino transport is not esp_http; /esp routes are compatibility status/proxy routes",
        }

    def _require_service() -> Any:
        if svc is None:
            raise HTTPException(status_code=503, detail="arduino service is not mounted")
        return svc

    def _safe_call(fn):
        try:
            return fn()
        except HTTPException:
            raise
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @router.get("/healthz")
    def healthz():
        return _state()

    @router.get("/status")
    def status():
        return _state()

    @router.post("/send")
    def send(obj: Dict[str, Any]):
        target = _require_service()
        return _safe_call(lambda: (target.send(obj), {"ok": True})[1])

    @router.post("/request")
    def request(obj: Dict[str, Any], timeout: float = 1.0):
        target = _require_service()
        return _safe_call(lambda: {"ok": True, "resp": target.request(obj, timeout=timeout)})

    started["esp_link"] = {
        "kind": "compat_router",
        "backend": "arduino_serial",
        "esp_mode": bool(getattr(svc, "_esp_mode", False)) if svc is not None else False,
    }
    app.include_router(router)
    logger.info("module esp_link mounted as arduino_serial ESP compatibility router")


def _include_neopixel(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.visual_output.neopixel.services.runner import NeoRunner  # type: ignore
    from modules.visual_output.neopixel.services.driver import NeoDriverConfig  # type: ignore
    from modules.visual_output.neopixel.config_loader import load_config as load_neo_cfg  # type: ignore
    from modules.visual_output.neopixel.api.router import get_router as get_neopixel_router  # type: ignore

    ncfg = _merge_with_agent_section(load_neo_cfg(None), "neopixel")
    hw = ncfg.get("hardware", {})
    cfg_obj = NeoDriverConfig(
        device=str(hw.get("device", "/dev/spidev0.0")),
        num_leds=int(hw.get("num_leds", 30)),
        speed_khz=int(hw.get("speed_khz", 800)),
        ws2812_spi_khz=int(hw.get("ws2812_spi_khz", 2400)),
        backend=str(hw.get("backend", "auto")),
        order=str(hw.get("order", "GRB")),
    )
    preset_meta = ncfg.get("presets_meta", {}) if isinstance(ncfg.get("presets_meta", {}), dict) else {}
    preset_store = Path(__file__).resolve().parents[2] / "neopixel" / "config" / "config.yml"
    runner = NeoRunner(
        cfg_obj,
        segments=hw.get("segments", []),
        presets=ncfg.get("presets", {}),
        preset_store_path=str(preset_store),
        preset_version=int(preset_meta.get("version", 1)),
        companion_cfg=ncfg.get("companion", {}),
    )
    started["neopixel"] = runner
    try:
        app.include_router(get_neopixel_router(runner))
    except Exception:
        pass
    logger.info("module neopixel mounted")


def _include_camera(app: FastAPI, started: Dict[str, object]) -> None:
    # sentrybot_windows_no_hardware_camera_stub
    import os

    if str(os.getenv("SENTRYBOT_NO_HARDWARE", "")).lower() in {"1", "true", "yes", "on"} or str(os.getenv("SENTRYBOT_SKIP_CAMERA_AUTOSTART", "")).lower() in {"1", "true", "yes", "on"}:
        from fastapi import APIRouter

        router = APIRouter(prefix="/camera", tags=["camera"])

        @router.get("/healthz")
        def _camera_stub_healthz():
            return {
                "ok": True,
                "available": False,
                "skipped": True,
                "reason": "hardware_disabled",
            }

        @router.get("/status")
        def _camera_stub_status():
            return {
                "ok": True,
                "available": False,
                "skipped": True,
                "reason": "hardware_disabled",
            }

        started["camera"] = {
            "kind": "stub",
            "available": False,
            "skipped": True,
            "reason": "hardware_disabled",
        }
        started["camera_handle"] = None
        started["onsensor_bus"] = None
        started["imx500_runner"] = None
        started["device_manager"] = None

        try:
            app.include_router(router)
        except Exception:
            pass

        logger.info("module camera mounted as no-hardware stub")
        return
    from modules.camera.api import get_router as get_cam_router  # type: ignore
    from modules.camera.config_loader import load_config as load_cam_cfg  # type: ignore
    from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher  # type: ignore
    from modules.camera.services.imx500_runner import Imx500Config, Imx500Runner  # type: ignore
    from modules.camera.services.onsensor_bus import get_default_bus  # type: ignore
    from modules.camera.device_manager import get_camera_manager, CameraConfig, CameraMode  # type: ignore

    ccfg = _merge_with_agent_section(load_cam_cfg(None), "camera")
    camera_enabled = bool(ccfg.get("enabled", True))
    picam_raw = ccfg.get("picamera2", {}) if isinstance(ccfg.get("picamera2"), dict) else {}
    size_raw = picam_raw.get("size", {}) if isinstance(picam_raw.get("size"), dict) else {}
    imx_raw = ccfg.get("imx500", {}) if isinstance(ccfg.get("imx500"), dict) else {}
    tracker_raw = imx_raw.get("tracker", {}) if isinstance(imx_raw.get("tracker"), dict) else {}
    target_raw = imx_raw.get("target", {}) if isinstance(imx_raw.get("target"), dict) else {}

    bus = get_default_bus()
    runner = Imx500Runner(
        Imx500Config(
            enabled=bool(imx_raw.get("enabled", True)),
            model_path=str(
                imx_raw.get(
                    "model_path",
                    "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk",
                )
            ),
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
    if camera_enabled:
        runner.prepare()

    # Initialize device manager
    cam_mode = CameraMode.LOCAL
    if ccfg.get("processing_mode") == "onsensor":
        cam_mode = CameraMode.ONSENSOR
    elif ccfg.get("hybrid_local_capture"):
        cam_mode = CameraMode.HYBRID
    elif ccfg.get("processing_mode") == "remote":
        cam_mode = CameraMode.REMOTE

    cam_config = CameraConfig(
        device="/dev/video0",
        width=int(size_raw.get("width", 1280)),
        height=int(size_raw.get("height", 720)),
        fps=int(picam_raw.get("frame_rate", ccfg.get("fps_target", 30))),
        format=str(picam_raw.get("format", "RGB888")),
        mode=cam_mode,
        imx500_enabled=bool(imx_raw.get("enabled", True)),
    )

    device_manager = get_camera_manager()
    device_manager.configure(cam_config)

    if camera_enabled:
        # Acquire device reference for camera capture
        cam_handle = device_manager.acquire("camera_capture", cam_mode)
        
        capture = CameraCapture(
            CaptureConfig(
                size=(int(size_raw.get("width", 1280)), int(size_raw.get("height", 720))),
                pixel_format=str(picam_raw.get("format", "RGB888")),
                frame_rate=int(picam_raw.get("frame_rate", ccfg.get("fps_target", 30))),
                jpeg_quality=int(ccfg.get("jpeg_quality", 80)),
                flip=str(ccfg.get("flip", "none")),
                camera_num=runner.camera_num,
            ),
            FramePublisher(),
        )

        if camera_enabled and _should_autostart_services():
            capture.start()
            runner.attach_camera(capture.picam, capture)
            runner.start()
        elif not camera_enabled:
            logger.info("camera disabled")
        else:
            logger.info("camera auto-start skipped")

        started["camera"] = capture
        started["camera_handle"] = cam_handle
        started["onsensor_bus"] = bus
        started["imx500_runner"] = runner
        fps_val = int(picam_raw.get("frame_rate", ccfg.get("fps_target", 30)))
        try:
            app.include_router(
                get_cam_router(
                    capture,
                    fps_val,
                    enabled=camera_enabled,
                    imx500_runner=runner,
                    onsensor_bus=bus,
                ),
                prefix="/camera",
                tags=["camera"],
            )
        except Exception as exc:
            logger.error("failed to mount camera router: %s", exc)
        logger.info("module camera mounted")


def _include_piservo(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.expression.piservo.config_loader import load_config as load_piservo_cfg  # type: ignore
    from modules.expression.piservo.api.router import get_router as get_piservo_router  # type: ignore
    from modules.expression.piservo.services.driver import ServoConfig  # type: ignore
    from modules.expression.piservo.services.runner import EarRunner  # type: ignore

    pcfg = _merge_with_agent_section(load_piservo_cfg(None), "piservo")
    left_raw = dict(pcfg.get("left", {"gpio": 12}))
    right_raw = dict(pcfg.get("right", {"gpio": 13}))
    if started.get("arduino") is not None:
        left_raw.pop("arduino_index", None)
        right_raw.pop("arduino_index", None)
    left = ServoConfig(**left_raw)
    right = ServoConfig(**right_raw)
    ears = EarRunner(left_cfg=left, right_cfg=right)
    started["piservo"] = ears
    app.include_router(get_piservo_router(ears))
    logger.info("module piservo mounted")


def _wire_arduino_neopixel(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    arduino = started.get("arduino")
    neopixel = started.get("neopixel")
    if arduino is None or neopixel is None or not hasattr(arduino, "register_event_handler"):
        return
    import threading

    bridge_cfg = cfg.get("arduino_neopixel_bridge", {})
    bridge_cfg = bridge_cfg if isinstance(bridge_cfg, dict) else {}
    lease_cfg = bridge_cfg.get("expression_lease", {})
    lease_cfg = lease_cfg if isinstance(lease_cfg, dict) else {}
    lease_enabled = bool(lease_cfg.get("enabled", False))
    lease_source = str(lease_cfg.get("source") or "").strip()
    lease_priority = lease_cfg.get("priority")
    lease_ttl_s = lease_cfg.get("ttl_s")
    lease_force = bool(lease_cfg.get("force", False))

    _np_lock = threading.Lock()
    _np_queue: list[Dict[str, Any]] = []
    _np_last_ms = 0
    _np_min_interval_ms = int(cfg.get("neopixel", {}).get("min_interval_ms", 100))
    _np_max_queue = int(cfg.get("neopixel", {}).get("max_queue", 32))

    def _enqueue_np(req: Dict[str, Any]) -> None:
        nonlocal _np_queue
        with _np_lock:
            if len(_np_queue) >= _np_max_queue:
                _np_queue.pop(0)
            _np_queue.append(req)

    def _flush_queue() -> None:
        nonlocal _np_last_ms
        now_ms = int(__import__("time").time() * 1000)
        with _np_lock:
            if not _np_queue:
                return
            if now_ms - _np_last_ms < _np_min_interval_ms:
                return
            req = _np_queue.pop(0)
        if lease_enabled:
            arbiter = started.get("expression_arbiter")
            if arbiter is None or not lease_source or not hasattr(arbiter, "claim_lights"):
                logger.warning("arduino neopixel request rejected: expression lease is unavailable")
                return
            if not arbiter.claim_lights(
                lease_source,
                force=lease_force,
                priority=lease_priority,
                ttl_s=lease_ttl_s,
            ):
                logger.debug("arduino neopixel request rejected by expression lease")
                return
        try:
            name = str(req.get("name", "")).strip()
            iterations = int(req.get("iterations", 1) or 1)
            if iterations < 1:
                iterations = 1
            if iterations > 10:
                iterations = 10
            color = None
            if isinstance(req.get("color"), str):
                parts = [p.strip() for p in str(req.get("color")).split(",")]
                if len(parts) == 3:
                    color = (int(parts[0]) & 255, int(parts[1]) & 255, int(parts[2]) & 255)
            segment = req.get("segment")
            if name:
                neopixel.animate(name=name, iterations=iterations, color=color, segment=segment)
            elif color is not None:
                if segment:
                    neopixel.fill(*color, segment=segment)
                else:
                    neopixel.fill(*color)
        except Exception as exc:
            logger.debug("neopixel request handling failed during flush: %s", exc)
        _np_last_ms = int(__import__("time").time() * 1000)

    def _on_arduino_event(msg: Dict[str, Any]) -> None:
        if not isinstance(msg, dict):
            return
        if msg.get("event") != "neopixel_request":
            return
        try:
            _enqueue_np(msg)
            _flush_queue()
        except Exception as exc:
            logger.debug("neopixel request handling failed: %s", exc)

    try:
        arduino.register_event_handler(_on_arduino_event)
        logger.info("arduino->neopixel event bridge mounted (rate-limited)")
    except Exception as exc:
        logger.warning("arduino->neopixel bridge mount failed: %s", exc)


def _wire_arduino_autonomy(started: Dict[str, object]) -> None:
    arduino = started.get("arduino")
    autonomy = started.get("autonomy")
    if arduino is None or autonomy is None or not hasattr(arduino, "register_event_handler"):
        return
    brain = getattr(autonomy, "brain", None)
    if not brain or not hasattr(brain, "handle_hardware_event"):
        return

    def _on_arduino_hardware_event(msg: Dict[str, Any]) -> None:
        if not isinstance(msg, dict):
            return
        event_name = msg.get("event")
        cmd_name = msg.get("cmd")

        if cmd_name == "estop" or event_name == "estop":
            try:
                brain.handle_hardware_event("estop", msg)
            except Exception:
                pass

        if not event_name:
            return

        hardware_events = {
            "cliff",
            "bump",
            "impact",
            "obstacle_imminent",
            "cliff_detected",
            "ultra_dist",
        }
        if event_name in hardware_events:
            try:
                brain.handle_hardware_event(event_name, msg)
            except Exception as exc:
                logger.debug("arduino hardware event routing to autonomy failed: %s", exc)

    try:
        arduino.register_event_handler(_on_arduino_hardware_event)
        logger.info("arduino hardware -> autonomy reflex engine bridge mounted")
    except Exception as exc:
        logger.warning("arduino->autonomy bridge mount failed: %s", exc)


def _wire_onsensor_vlm(started: Dict[str, object]) -> None:
    vlm_bridge = started.get("vlm_bridge")
    bus = started.get("onsensor_bus")
    if vlm_bridge is not None and bus is not None and hasattr(vlm_bridge, "attach_onsensor_bus"):
        try:
            vlm_bridge.attach_onsensor_bus(bus)
            logger.info("onsensor bus -> vlm_bridge subscriber attached")
        except Exception as exc:
            logger.warning("onsensor bus attach failed: %s", exc)


def _wire_animate_piservo(started: Dict[str, object]) -> None:
    anim = started.get("animate")
    if anim is None:
        return
    ears = started.get("piservo")
    if ears is not None and hasattr(anim, "attach_ears"):
        try:
            anim.attach_ears(ears)
            logger.info("animate -> piservo ear channels attached")
        except Exception as exc:
            logger.warning("animate piservo attach failed: %s", exc)
    oled = started.get("oled_faces")
    if oled is not None and hasattr(anim, "attach_oled"):
        try:
            anim.attach_oled(oled)
            logger.info("animate -> oled_faces visual channel attached")
        except Exception as exc:
            logger.warning("animate oled attach failed: %s", exc)
    neo = started.get("neopixel")
    if neo is not None and hasattr(anim, "attach_neopixel"):
        try:
            anim.attach_neopixel(neo)
            logger.info("animate -> neopixel lighting channel attached")
        except Exception as exc:
            logger.warning("animate neopixel attach failed: %s", exc)


def _wire_interactions_piservo(started: Dict[str, object]) -> None:
    interactions = started.get("interactions")
    piservo = started.get("piservo")
    if interactions is None or piservo is None or not hasattr(interactions, "register_event_handler"):
        return
    _ear_gesture_events = {
        "wakeword.detected": "wakeword",
        "sound.detected": "sound",
        "vision.focus": "sound",
        "vision.person": "sound",
        "environment.scene_changed": "sound",
    }

    def _piservo_on_interaction(evt: str, data: Dict[str, Any]) -> None:
        key = str(evt or "").strip().lower()
        try:
            if key.startswith("emotion:") and hasattr(piservo, "emotion"):
                piservo.emotion(key.split(":", 1)[1])
                return
            gesture = _ear_gesture_events.get(key)
            if gesture and hasattr(piservo, "gesture"):
                piservo.gesture(gesture)
        except Exception:
            pass

    try:
        interactions.register_event_handler(_piservo_on_interaction)
        logger.info("interactions -> piservo ear expression bridge mounted")
    except Exception as exc:
        logger.warning("piservo interactions bridge mount failed: %s", exc)
