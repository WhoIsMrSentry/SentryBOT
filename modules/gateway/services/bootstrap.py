from __future__ import annotations
from typing import Dict, Any

import logging

from fastapi import FastAPI

logger = logging.getLogger("gateway.bootstrap")


def _include_arduino(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.api.router import get_router as get_arduino_router  # type: ignore
    ardu = xArduinoSerialService()
    try:
        ardu.start()
    except Exception as exc:
        logger.warning("Arduino serial service failed to start, running degraded: %s", exc)
    started["arduino"] = ardu
    app.include_router(get_arduino_router(ardu))


def _include_vision_bridge(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.vision_bridge.api.router import get_router as get_vision_router  # type: ignore
    app.include_router(get_vision_router(started.get("arduino")))
    started["vision_bridge"] = True


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
        order=str(hw.get("order", "GRB")),
    )
    runner = NeoRunner(cfg_obj)
    started["neopixel"] = runner
    app.include_router(get_neopixel_router(runner))


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
    eng = InteractionEngine(icfg)
    eng.start()
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
    app.include_router(get_speech_router(svc))
    logger.info("module speech mounted")


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


def _include_wiki_rag(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.wiki_rag.config_loader import load_config as load_wiki_cfg  # type: ignore
    from modules.wiki_rag.api.router import get_router as get_wiki_router  # type: ignore
    wcfg = load_wiki_cfg(None)
    app.include_router(get_wiki_router(wcfg), prefix="/wiki_rag")
    started["wiki_rag"] = True
    logger.info("module wiki_rag mounted")


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
    capture.start()
    app.include_router(get_cam_router(capture, cap_cfg.fps_target), prefix="/camera", tags=["camera"])
    started["camera"] = capture
    logger.info("module camera mounted")


def _include_animate(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.animate.xAnimateService import xAnimateService  # type: ignore
    from modules.animate.api.router import get_router as get_anim_router  # type: ignore
    ardu = started.get("arduino")
    anim = xAnimateService(serial=ardu) if ardu is not None else xAnimateService()
    if hasattr(anim, "start"):
        anim.start()
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
    svc.start()
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

        app.add_event_handler("startup", _start_bot)
        app.add_event_handler("shutdown", _stop_bot)

    started["notifier"] = True
    logger.info("module notifier mounted")


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
    if include.get("vision_bridge"):
        _try(lambda: _include_vision_bridge(app, started), "vision_bridge")
    if include.get("neopixel"):
        _try(lambda: _include_neopixel(app, started), "neopixel")
    if include.get("interactions"):
        _try(lambda: _include_interactions(app, started, cfg), "interactions")
    if include.get("speak"):
        _try(lambda: _include_speak(app, started), "speak")
    if include.get("speech"):
        _try(lambda: _include_speech(app, started), "speech")
    if include.get("ollama"):
        _try(lambda: _include_ollama(app, started), "ollama")
    if include.get("logs"):
        _try(lambda: _include_logs(app, started), "logs")
    if include.get("wiki_rag"):
        _try(lambda: _include_wiki_rag(app, started), "wiki_rag")
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

    return started
