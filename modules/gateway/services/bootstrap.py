from __future__ import annotations
from typing import Dict, Any
import os

import logging

from fastapi import FastAPI
import warnings

# Suppress specific FastAPI deprecation about on_event (we prefer add_event_handler when available)
warnings.filterwarnings("ignore", message=".*on_event is deprecated.*", category=DeprecationWarning)

logger = logging.getLogger("gateway.bootstrap")


def _should_autostart_services() -> bool:
    """Disable heavy background starts unless explicitly enabled.

    Priority:
    1) SENTRYBOT_FORCE_AUTOSTART=true => always start
    2) SENTRYBOT_DISABLE_AUTOSTART=true => never start
    3) PYTEST_CURRENT_TEST set => never start
    4) default => start
    """
    force = str(os.getenv("SENTRYBOT_FORCE_AUTOSTART", "")).strip().lower()
    if force in {"1", "true", "yes", "on"}:
        return True

    disable = str(os.getenv("SENTRYBOT_DISABLE_AUTOSTART", "")).strip().lower()
    if disable in {"1", "true", "yes", "on"}:
        return False

    return not bool(os.getenv("PYTEST_CURRENT_TEST"))


def _include_arduino(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.api.router import get_router as get_arduino_router  # type: ignore
    ardu = xArduinoSerialService()
    if _should_autostart_services():
        try:
            ardu.start()
        except Exception as exc:
            logger.warning("arduino service failed to start, running degraded: %s", exc)
    else:
        logger.info("arduino auto-start skipped (autostart disabled)")

    started["arduino"] = ardu
    # mount the arduino router so other modules can talk to it
    try:
        app.include_router(get_arduino_router(ardu))
    except Exception:
        # router may not be available in degraded mode
        pass
    logger.info("module arduino mounted")

def _include_neopixel(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.neopixel.services.runner import NeoRunner  # type: ignore
    from modules.neopixel.services.driver import NeoDriverConfig  # type: ignore
    from modules.neopixel.config_loader import load_config as load_neo_cfg  # type: ignore
    from modules.neopixel.api.router import get_router as get_neopixel_router  # type: ignore

    ncfg = load_neo_cfg(None)
    hw = ncfg.get("hardware", {})
    cfg_obj = NeoDriverConfig(
        device=str(hw.get("device", "/dev/spidev0.0")),
        num_leds=int(hw.get("num_leds", 30)),
        speed_khz=int(hw.get("speed_khz", 800)),
        ws2812_spi_khz=int(hw.get("ws2812_spi_khz", 2400)),
        backend=str(hw.get("backend", "auto")),
        order=str(hw.get("order", "GRB")),
    )
    runner = NeoRunner(cfg_obj)
    started["neopixel"] = runner
    try:
        app.include_router(get_neopixel_router(runner))
    except Exception:
        # router mount may fail in degraded/no-driver environments
        pass
    logger.info("module neopixel mounted")


def _include_vlm_bridge(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.vlm_bridge.config_loader import load_config as load_vlm_cfg  # type: ignore
    from modules.vlm_bridge.services.processor import VisionProcessor  # type: ignore
    from modules.vlm_bridge.api.router import get_router as get_vlm_router  # type: ignore

    vcfg = load_vlm_cfg(None)
    processor = VisionProcessor(vcfg)
    ardu = started.get("arduino")
    if ardu is not None and hasattr(processor, "set_track_callback") and hasattr(ardu, "track"):
        def _track_callback(head_pan: float, head_tilt: float, drive: int = 0):
            try:
                return ardu.track(head_pan=float(head_pan), head_tilt=float(head_tilt), drive=int(drive))
            except Exception:
                return None
        processor.set_track_callback(_track_callback)

    if _should_autostart_services() and str(vcfg.get("vision", {}).get("processing_mode", "local")).strip().lower() == "local":
        try:
            processor.start_stream_processing()
        except Exception as exc:
            logger.warning("vlm_bridge stream start skipped: %s", exc)
    # Mount router and expose processor so other modules can reference it
    try:
        app.include_router(get_vlm_router(processor, started.get("arduino")))
    except Exception:
        # If router mount fails, continue in degraded mode
        pass
    started["vlm_bridge"] = processor
    logger.info("module vlm_bridge mounted")


def _include_interactions(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.interactions.api.router import get_router as get_inter_router  # type: ignore
    from modules.interactions.config_loader import load_config as load_inter_cfg  # type: ignore
    from modules.interactions.services.engine import InteractionEngine  # type: ignore
    icfg = load_inter_cfg(None)
    # Force interactions to talk to gateway's neopixel endpoint instead of standalone 8092
    try:
        port = int(cfg.get("server", {}).get("port", 8080))
        icfg.setdefault("adapter", {})["http_base_url"] = f"http://127.0.0.1:{port}/neopixel"
    except Exception:
        pass
    # If neopixel runner is already started in-process, pass it to InteractionEngine
    eng = InteractionEngine(icfg, neo_client=started.get("neopixel"))
    if _should_autostart_services():
        eng.start()
    else:
        logger.info("interactions auto-start skipped (autostart disabled)")
    started["interactions"] = eng
    app.include_router(get_inter_router(eng))


def _include_speak(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.speak.xSpeakService import SpeakService  # type: ignore
    from modules.speak.api.router import get_router as get_speak_router  # type: ignore
    svc = SpeakService()
    started["speak"] = svc
    app.include_router(get_speak_router(svc))
    logger.info("module speak mounted")


def _include_speech(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.speech.xSpeechService import SpeechService  # type: ignore
    from modules.speech.api import get_router as get_speech_router  # type: ignore
    svc = SpeechService()
    started["speech"] = svc
    # If gateway config requests speech to start listening on boot, start it.
    try:
        # cfg is passed to bootstrap and available in outer scope; read flag if present
        # default: do not auto-start listening here (wakeword handles triggers)
        # We attempt to read top-level 'speech' config under gateway config for this flag.
        from modules.gateway import config_loader as _gw_cfg  # type: ignore
        gwcfg = _gw_cfg.load_config(None)
        if isinstance(gwcfg.get("speech"), dict) and bool(gwcfg.get("speech", {}).get("listening", False)):
            try:
                svc.start_background()
            except Exception:
                pass
    except Exception:
        pass
    app.include_router(get_speech_router(svc))
    logger.info("module speech mounted")


def _include_wakeword(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.wakeword.xWakewordService import WakewordService  # type: ignore
    from modules.wakeword.api import get_router as get_wakeword_router  # type: ignore
    svc = WakewordService()
    if _should_autostart_services():
        svc.start_background()
    else:
        logger.info("wakeword auto-start skipped (autostart disabled)")
    started["wakeword"] = svc
    app.include_router(get_wakeword_router(svc))
    logger.info("module wakeword mounted")


def _include_ollama(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.ollama.config_loader import load_config as load_ollama_cfg  # type: ignore
    from modules.ollama.api.router import get_router as get_ollama_router  # type: ignore
    ocfg = load_ollama_cfg(None)
    app.include_router(get_ollama_router(ocfg))
    started["ollama"] = True
    logger.info("module ollama mounted")


def _include_logs(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.logwrapper import get_router as get_logs_router  # type: ignore
    logs_router = get_logs_router()
    if logs_router is not None:
        app.include_router(logs_router)
        started["logs"] = True
        logger.info("module logs mounted")


def _include_camera(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.camera.config_loader import load_config as load_cam_cfg  # type: ignore
    from modules.camera.services.capture import CameraCapture, FramePublisher, CaptureConfig  # type: ignore
    from modules.camera.api import get_router as get_cam_router  # type: ignore
    ccfg = load_cam_cfg(None)
    cap_cfg = CaptureConfig(
        backend=ccfg.get("backend", "auto"),
        source=ccfg.get("source", 0),
        resolution=(int(ccfg.get("resolution", {}).get("width", 1280)), int(ccfg.get("resolution", {}).get("height", 720))),
        fps_target=int(ccfg.get("fps_target", 30)),
        jpeg_quality=int(ccfg.get("jpeg_quality", 80)),
        opencv_fourcc=str(ccfg.get("opencv", {}).get("fourcc", "MJPG")),
        opencv_buffer_size=int(ccfg.get("opencv", {}).get("buffer_size", 1)),
        picam_size=(int(ccfg.get("picamera2", {}).get("size", {}).get("width", 1920)), int(ccfg.get("picamera2", {}).get("size", {}).get("height", 1080))),
        picam_format=str(ccfg.get("picamera2", {}).get("format", "RGB888")),
        picam_frame_rate=int(ccfg.get("picamera2", {}).get("frame_rate", 30)),
        picam_af_mode=int(ccfg.get("picamera2", {}).get("af_mode", 2)),
        flip=str(ccfg.get("flip", "none")),
    )
    publisher = FramePublisher()
    capture = CameraCapture(cap_cfg, publisher)
    if _should_autostart_services():
        capture.start()
    else:
        logger.info("camera auto-start skipped (autostart disabled)")
    app.include_router(get_cam_router(capture, cap_cfg.fps_target), prefix="/camera", tags=["camera"])
    started["camera"] = capture
    logger.info("module camera mounted")


def _include_animate(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.animate.xAnimateService import xAnimateService  # type: ignore
    from modules.animate.api.router import get_router as get_anim_router  # type: ignore
    ardu = started.get("arduino")
    anim = xAnimateService(serial=ardu) if ardu is not None else xAnimateService()
    if _should_autostart_services() and hasattr(anim, "start"):
        try:
            anim.start()
        except Exception as exc:
            logger.warning("animate service failed to start, running degraded: %s", exc)
    elif hasattr(anim, "start"):
        logger.info("animate auto-start skipped (autostart disabled)")
    started["animate"] = anim
    app.include_router(get_anim_router(anim))
    logger.info("module animate mounted")


def _include_piservo(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.piservo.config_loader import load_config as load_piservo_cfg  # type: ignore
    from modules.piservo.api.router import get_router as get_piservo_router  # type: ignore
    from modules.piservo.services.driver import ServoConfig  # type: ignore
    from modules.piservo.services.runner import EarRunner  # type: ignore
    pcfg = load_piservo_cfg(None)
    left = ServoConfig(**pcfg.get("left", {"gpio": 12}))
    right = ServoConfig(**pcfg.get("right", {"gpio": 13}))
    ears = EarRunner(left_cfg=left, right_cfg=right)
    started["piservo"] = ears
    app.include_router(get_piservo_router(ears))
    logger.info("module piservo mounted")


def _include_autonomy(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.autonomy.xAutonomyService import xAutonomyService  # type: ignore
    from modules.autonomy.api.router import get_router as get_autonomy_router  # type: ignore
    svc = xAutonomyService()
    if _should_autostart_services():
        svc.start()
    else:
        logger.info("autonomy auto-start skipped (autostart disabled)")
    started["autonomy"] = svc
    app.include_router(get_autonomy_router(svc.brain))
    logger.info("module autonomy mounted")


def _include_notifier(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.notifier.config_loader import load_config as load_not_cfg  # type: ignore
    from modules.notifier.api.router import get_router as get_notifier_router  # type: ignore
    from modules.notifier.services.telegram_bot import build_telegram_bot  # type: ignore

    ncfg = load_not_cfg(None)
    bot = build_telegram_bot(ncfg)
    app.include_router(get_notifier_router(ncfg, bot))
    polling_enabled = ncfg.get("telegram", {}).get("polling", {}).get("enabled", False)
    if bot and polling_enabled:
        async def _start_bot() -> None:
            logger.info("notifier: starting telegram polling via gateway")
            await bot.start()

        async def _stop_bot() -> None:
            logger.info("notifier: stopping telegram polling via gateway")
            await bot.stop()

        # Prefer add_event_handler when available; fall back to on_event decorator
        if hasattr(app, "add_event_handler"):
            app.add_event_handler("startup", _start_bot)
            app.add_event_handler("shutdown", _stop_bot)
        elif hasattr(app, "on_event"):
            # `on_event` is deprecated in newer FastAPI versions; suppress the deprecation
            # warning when falling back so logs are not noisy on older platforms.
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    app.on_event("startup")(_start_bot)
                    app.on_event("shutdown")(_stop_bot)
            except Exception:
                # If even this fails, fall back to warning and skip auto-start.
                logger.warning("notifier: on_event fallback failed; polling not auto-started")
        else:
            logger.warning("notifier: app lacks event registration API; polling not auto-started")

    started["notifier"] = True
    logger.info("module notifier mounted")


def _include_oled_faces(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.oled_faces.xOledFacesService import xOledFacesService  # type: ignore
    from modules.oled_faces.api.router import get_router as get_oled_faces_router  # type: ignore

    state_store = started.get("state_manager")
    interactions = started.get("interactions")

    svc = xOledFacesService(state_store=state_store)

    if interactions is not None and hasattr(interactions, "register_event_handler"):
        try:
            interactions.register_event_handler(svc.on_interaction_event)
        except Exception as exc:
            logger.warning("oled_faces interactions handler attach failed: %s", exc)

    try:
        svc.start()
    except Exception as exc:
        logger.warning("oled_faces failed to start, running degraded: %s", exc)

    started["oled_faces"] = svc
    app.include_router(get_oled_faces_router(svc))
    logger.info("module oled_faces mounted")


def bootstrap(app: FastAPI, cfg: Dict[str, Any]) -> Dict[str, object]:
    """Start and wire modules according to cfg.include and return started dict."""
    started: Dict[str, object] = {}

    include = cfg.get("include", {})

    def _try(fn, name: str = ""):
        try:
            fn()
        except Exception as exc:
            logger.warning("module %s failed to mount: %s", name or fn.__name__, exc)

    if include.get("arduino"):
        _try(lambda: _include_arduino(app, started), "arduino")
    if include.get("vlm_bridge"):
        _try(lambda: _include_vlm_bridge(app, started), "vlm_bridge")
    if include.get("neopixel"):
        _try(lambda: _include_neopixel(app, started), "neopixel")
    if include.get("interactions"):
        _try(lambda: _include_interactions(app, started, cfg), "interactions")
    if include.get("speak"):
        _try(lambda: _include_speak(app, started), "speak")
    if include.get("speech"):
        _try(lambda: _include_speech(app, started), "speech")
    if include.get("wakeword"):
        _try(lambda: _include_wakeword(app, started), "wakeword")
    if include.get("ollama"):
        _try(lambda: _include_ollama(app, started), "ollama")
    if include.get("logs"):
        _try(lambda: _include_logs(app, started), "logs")
    if include.get("camera"):
        _try(lambda: _include_camera(app, started), "camera")
    if include.get("animate"):
        _try(lambda: _include_animate(app, started), "animate")
    if include.get("piservo"):
        _try(lambda: _include_piservo(app, started), "piservo")
    if include.get("autonomy"):
        _try(lambda: _include_autonomy(app, started), "autonomy")

    # optional: mutagen
    if include.get("mutagen"):
        _try(lambda: app.include_router(__import__("modules.mutagen.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.mutagen.config_loader", fromlist=["load_config"]).load_config(None)
        )), "mutagen")
        started["mutagen"] = True

    # optional: ota
    if include.get("ota"):
        _try(lambda: app.include_router(__import__("modules.ota.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.ota.config_loader", fromlist=["load_config"]).load_config(None)
        )), "ota")
        started["ota"] = True

    # new optional modules
    if include.get("hardware"):
        _try(lambda: app.include_router(__import__("modules.hardware.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.hardware.config_loader", fromlist=["load_config"]).load_config(None)
        )), "hardware")
        started["hardware"] = True

    if include.get("telemetry"):
        _try(lambda: app.include_router(__import__("modules.telemetry.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.telemetry.config_loader", fromlist=["load_config"]).load_config(None)
        )), "telemetry")
        started["telemetry"] = True

    if include.get("diagnostics"):
        _try(lambda: app.include_router(__import__("modules.diagnostics.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.diagnostics.config_loader", fromlist=["load_config"]).load_config(None)
        )), "diagnostics")
        started["diagnostics"] = True

    if include.get("state_manager"):
        def _mount_state():
            cfg_sm = __import__("modules.state_manager.config_loader", fromlist=["load_config"]).load_config(None)
            StateStore = __import__("modules.state_manager.services.store", fromlist=["StateStore"]).StateStore
            get_router = __import__("modules.state_manager.api.router", fromlist=["get_router"]).get_router
            store = StateStore(cfg_sm.get("defaults", {}))
            started["state_manager"] = store
            app.include_router(get_router(store))
        _try(_mount_state, "state_manager")

    if include.get("oled_faces"):
        _try(lambda: _include_oled_faces(app, started), "oled_faces")

    if include.get("scheduler"):
        _try(lambda: app.include_router(__import__("modules.scheduler.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.scheduler.config_loader", fromlist=["load_config"]).load_config(None)
        )), "scheduler")
        started["scheduler"] = True

    if include.get("notifier"):
        _try(lambda: _include_notifier(app, started), "notifier")

    if include.get("calibration"):
        _try(lambda: app.include_router(__import__("modules.calibration.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.calibration.config_loader", fromlist=["load_config"]).load_config(None)
        )), "calibration")
        started["calibration"] = True

    if include.get("config_center"):
        _try(lambda: app.include_router(__import__("modules.config_center.api.router", fromlist=["get_router"]).get_router(
            __import__("modules.config_center.config_loader", fromlist=["load_config"]).load_config(None)
        )), "config_center")
        started["config_center"] = True

    arduino = started.get("arduino")
    neopixel = started.get("neopixel")
    if arduino is not None and neopixel is not None and hasattr(arduino, "register_event_handler"):
        # rate-limited queue to prevent NeoPixel overload from Arduino bursts
        import threading
        _np_lock = threading.Lock()
        _np_queue: list[Dict[str, Any]] = []
        _np_last_ms = 0
        _np_min_interval_ms = int(cfg.get("neopixel", {}).get("min_interval_ms", 100))
        _np_max_queue = int(cfg.get("neopixel", {}).get("max_queue", 32))

        def _enqueue_np(req: Dict[str, Any]) -> None:
            nonlocal _np_queue
            with _np_lock:
                if len(_np_queue) >= _np_max_queue:
                    # drop oldest to make room
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
            try:
                name = str(req.get("name", "")).strip()
                iterations = int(req.get("iterations", 1) or 1)
                # clamp iterations
                if iterations < 1: iterations = 1
                if iterations > 10: iterations = 10
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
                # enqueue and attempt a flush
                _enqueue_np(msg)
                _flush_queue()
            except Exception as exc:
                logger.debug("neopixel request handling failed: %s", exc)

        try:
            arduino.register_event_handler(_on_arduino_event)
            logger.info("arduino->neopixel event bridge mounted (rate-limited)")
        except Exception as exc:
            logger.warning("arduino->neopixel bridge mount failed: %s", exc)

    return started


