from __future__ import annotations
from typing import Dict, Any, Optional
import os

import logging

from fastapi import FastAPI
import warnings

# Suppress specific FastAPI deprecation about on_event (we prefer add_event_handler when available)
warnings.filterwarnings("ignore", message=".*on_event is deprecated.*", category=DeprecationWarning)

logger = logging.getLogger("gateway.bootstrap")

_AGENT_CFG_CACHE: Optional[Dict[str, Any]] = None


def _root_agent_cfg() -> Dict[str, Any]:
    global _AGENT_CFG_CACHE
    if _AGENT_CFG_CACHE is not None:
        return _AGENT_CFG_CACHE
    try:
        from modules.config_center.agent_yaml_loader import load_agent_config  # type: ignore

        cfg = load_agent_config(None)
        _AGENT_CFG_CACHE = cfg if isinstance(cfg, dict) else {}
    except Exception:
        _AGENT_CFG_CACHE = {}
    return _AGENT_CFG_CACHE


def _agent_section(name: str) -> Dict[str, Any]:
    cfg = _root_agent_cfg()
    value = cfg.get(name, {}) if isinstance(cfg, dict) else {}
    return value if isinstance(value, dict) else {}


def _merge_with_agent_section(base_cfg: Dict[str, Any], section_name: str) -> Dict[str, Any]:
    section = _agent_section(section_name)
    if not section:
        return base_cfg
    try:
        from modules.config_center.agent_yaml_loader import deep_merge  # type: ignore

        return deep_merge(base_cfg, section)
    except Exception:
        merged = dict(base_cfg)
        merged.update(section)
        return merged


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


def _register_runtime_keys(registry: Any, started: Dict[str, object]) -> None:
    """Seed the runtime registry with hot-applyable keys exposed by modules.

    Each ``apply_fn`` updates the corresponding live instance, so the admin UI
    can flip vision modes, swap realtime profiles, or rebind autonomy hooks
    without restarting the gateway.
    """
    vlm_bridge = started.get("vlm_bridge")
    autonomy = started.get("autonomy")
    agent = None
    if autonomy is not None and hasattr(autonomy, "brain"):
        agent = getattr(autonomy.brain, "agent", None)

    def _vlm_apply_mode(key: str):
        def _apply(value: Any) -> Optional[Dict[str, Any]]:
            if vlm_bridge is None or not hasattr(vlm_bridge, "set_modes"):
                return None
            return vlm_bridge.set_modes({key: bool(value)})
        return _apply

    if vlm_bridge is not None and hasattr(vlm_bridge, "get_modes"):
        modes = vlm_bridge.get_modes() if callable(getattr(vlm_bridge, "get_modes", None)) else {}
        for mode_name, default in modes.items():
            registry.register(
                "vlm_bridge",
                f"modes.{mode_name}",
                type="bool",
                default=bool(default),
                description=f"Enable/disable VLM bridge mode '{mode_name}'.",
                apply_fn=_vlm_apply_mode(mode_name),
            )

        def _apply_profile(value: Any) -> Optional[Dict[str, Any]]:
            if not hasattr(vlm_bridge, "apply_mode_profile"):
                return None
            return vlm_bridge.apply_mode_profile(str(value))

        if hasattr(vlm_bridge, "list_profiles"):
            try:
                choices = tuple(vlm_bridge.list_profiles())
            except Exception:
                choices = None
            registry.register(
                "vlm_bridge",
                "mode_profile",
                type="choice",
                default="balanced",
                choices=choices,
                description="VLM bridge mode profile.",
                apply_fn=_apply_profile,
            )

        def _apply_realtime(value: Any) -> Optional[Dict[str, Any]]:
            if not hasattr(vlm_bridge, "apply_realtime_profile"):
                return None
            return vlm_bridge.apply_realtime_profile(str(value))

        registry.register(
            "vlm_bridge",
            "realtime_profile",
            type="choice",
            default="fast",
            choices=("fast", "normal"),
            description="VLM bridge realtime latency profile.",
            apply_fn=_apply_realtime,
        )

        def _apply_processing_mode(value: Any) -> Optional[Dict[str, Any]]:
            if vlm_bridge is None or not hasattr(vlm_bridge, "set_processing_mode"):
                return None
            return vlm_bridge.set_processing_mode(str(value or "local"))

        registry.register(
            "vlm_bridge",
            "vision.processing_mode",
            type="string",
            default="local",
            description="VLM bridge processing pipeline (local or remote)",
            apply_fn=_apply_processing_mode,
        )

        if hasattr(vlm_bridge, "get_mode_categories") and hasattr(vlm_bridge, "set_mode_categories"):
            try:
                categories = vlm_bridge.get_mode_categories()
            except Exception:
                categories = {}

            def _make_cat_apply(category: str, key: str):
                def _apply(value: Any) -> Optional[Dict[str, Any]]:
                    return vlm_bridge.set_mode_categories({category: {key: bool(value)}})
                return _apply

            for category, flags in categories.items():
                for key, default in flags.items():
                    registry.register(
                        "vlm_bridge",
                        f"mode_categories.{category}.{key}",
                        type="bool",
                        default=bool(default),
                        description=f"Enable/disable '{key}' under '{category}' vision pipeline.",
                        apply_fn=_make_cat_apply(category, key),
                    )

    if agent is not None:
        def _apply_agent_profile(value: Any) -> Optional[Dict[str, Any]]:
            mode = str(value or "").strip().lower()
            rt_cfg = agent.config.get("realtime_profile", {}) if isinstance(agent.config, dict) else {}
            if not isinstance(rt_cfg, dict):
                return {"ok": False, "error": "invalid_config"}
            profiles_map = rt_cfg.get("profiles", {}) if isinstance(rt_cfg.get("profiles", {}), dict) else {}
            profile = profiles_map.get(mode, {}) if mode else {}
            if not isinstance(profile, dict) or not profile:
                profile = rt_cfg.get(mode, {})
            if not isinstance(profile, dict) or not profile:
                return {"ok": False, "error": "unknown_profile"}
            rt_cfg["active"] = mode
            applied = agent.apply_realtime_profile(profile) if hasattr(agent, "apply_realtime_profile") else {}
            return {"ok": True, "applied": applied}

        registry.register(
            "agent_core",
            "realtime_profile",
            type="choice",
            default="normal",
            choices=None,
            description="Named Agent Core realtime profile (matches realtime_profile.profiles keys).",
            apply_fn=_apply_agent_profile,
        )

        def _apply_max_subagents(value: Any) -> Optional[Dict[str, Any]]:
            try:
                n = max(1, int(value))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid_value"}
            router = getattr(agent, "router", None)
            if router is None:
                return {"ok": False, "error": "no_router"}
            if hasattr(router, "set_max"):
                clamped = router.set_max(n)
                return {"ok": True, "max_subagents": clamped}
            if hasattr(router, "max_subagents"):
                router.max_subagents = n
            return {"ok": True, "max_subagents": getattr(router, "max_subagents", n)}

        registry.register(
            "agent_core",
            "max_subagents",
            type="int",
            default=2,
            minimum=1,
            maximum=8,
            description="Maximum concurrent sub-agents launched per request.",
            apply_fn=_apply_max_subagents,
        )

    imx_runner = started.get("imx500_runner")

    def _apply_imx500_enabled(value: Any) -> Optional[Dict[str, Any]]:
        if imx_runner is None:
            return {"ok": False, "error": "no_runner"}
        try:
            from modules.camera.services import imx500_runner as imx_mod  # type: ignore

            imx_runner.cfg.enabled = bool(value)
            imx_runner._available = bool(value) and bool(getattr(imx_mod, "IMX500_AVAILABLE", False))
            if imx_runner.available and imx_runner.cfg.enabled:
                imx_runner.start()
            else:
                imx_runner.stop()
            return {"ok": True, "enabled": imx_runner.cfg.enabled}
        except Exception as exc:
            logger.warning("IMX500 hot toggle failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _apply_imx500_conf(value: Any) -> Optional[Dict[str, Any]]:
        if imx_runner is None:
            return {"ok": False, "error": "no_runner"}
        try:
            imx_runner.cfg.confidence = float(value)
            return {"ok": True, "confidence": imx_runner.cfg.confidence}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    if imx_runner is not None:
        registry.register(
            "camera",
            "imx500.enabled",
            type="bool",
            default=bool(getattr(getattr(imx_runner, "cfg", None), "enabled", False)),
            description="Toggle IMX500 on-sensor inference loop.",
            apply_fn=_apply_imx500_enabled,
        )
        registry.register(
            "camera",
            "imx500.confidence",
            type="float",
            default=float(getattr(getattr(imx_runner, "cfg", None), "confidence", 0.45)),
            minimum=0.05,
            maximum=1.0,
            description="Confidence threshold forwarded to SSD post-filter.",
            apply_fn=_apply_imx500_conf,
        )

    state_manager = started.get("state_manager")
    if state_manager is not None and hasattr(state_manager, "set_operational"):
        def _apply_operational(value: Any) -> Optional[Dict[str, Any]]:
            state_manager.set_operational(str(value or "idle"))
            return {"ok": True, "operational": str(value or "idle")}

        registry.register(
            "state_manager",
            "operational",
            type="choice",
            default="idle",
            choices=("idle", "active", "sleep", "maintenance"),
            description="Global operational state for SentryBOT.",
            apply_fn=_apply_operational,
        )


def _include_admin_ui(app: FastAPI, started: Dict[str, object], gw_cfg: Dict[str, Any]) -> None:
    """Expose the consolidated operator dashboard plus REST aggregates."""
    from modules.admin_ui.api.router import mount as mount_admin_ui  # type: ignore
    from modules.admin_ui.config_loader import load_config as load_admin_cfg  # type: ignore

    admin_cfg = _merge_with_agent_section(load_admin_cfg(None), "admin_ui")
    server_blk = gw_cfg.get("server", {}) if isinstance(gw_cfg.get("server", {}), dict) else {}
    explicit_base = str(gw_cfg.get("gateway_base_url", "") or "").strip().rstrip("/")
    if explicit_base:
        started["gateway_base_url"] = explicit_base
    else:
        port = int(server_blk.get("port", 8080))
        started["gateway_base_url"] = f"http://127.0.0.1:{port}"
    mount_admin_ui(app, admin_cfg, started)
    started["admin_ui"] = True
    logger.info("module admin_ui mounted at prefix %s", admin_cfg.get("mount_prefix", "/admin"))


def _include_social_db(app: FastAPI, started: Dict[str, object]) -> None:
    """Initialise the shared SQLite social store before any consumer needs it."""
    from modules.social_db.config_loader import load_config as load_social_cfg  # type: ignore
    from modules.social_db.db import SocialDB, set_default  # type: ignore

    scfg = _merge_with_agent_section(load_social_cfg(None), "social_db")
    db = SocialDB(
        path=str(scfg.get("path", "data/social.sqlite3")),
        wal=bool(scfg.get("wal", True)),
        cache_size_kb=int(scfg.get("cache_size_kb", 4096)),
        busy_timeout_ms=int(scfg.get("busy_timeout_ms", 5000)),
        auto_migrate=bool(scfg.get("auto_migrate", True)),
    )
    set_default(db)
    started["social_db"] = db
    logger.info("module social_db mounted (path=%s)", db.path)


def _include_arduino(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
    from modules.arduino_serial.api.router import get_router as get_arduino_router  # type: ignore
    ardu = xArduinoSerialService(config_overrides=_agent_section("arduino_serial") or None)
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


def _include_esp_link(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.esp_link.xEspLinkService import xEspLinkService  # type: ignore
    from modules.esp_link.api.router import get_router as get_esp_router  # type: ignore

    svc = xEspLinkService()
    started["esp_link"] = svc
    app.include_router(get_esp_router(svc))
    logger.info("module esp_link mounted")

def _include_neopixel(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.neopixel.services.runner import NeoRunner  # type: ignore
    from modules.neopixel.services.driver import NeoDriverConfig  # type: ignore
    from modules.neopixel.config_loader import load_config as load_neo_cfg  # type: ignore
    from modules.neopixel.api.router import get_router as get_neopixel_router  # type: ignore

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
        app.include_router(
            get_vlm_router(
                processor,
                started.get("arduino"),
                gateway_base_url=str(started.get("gateway_base_url", "")),
            )
        )
    except Exception:
        # If router mount fails, continue in degraded mode
        pass
    started["vlm_bridge"] = processor
    logger.info("module vlm_bridge mounted")


def _include_interactions(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.interactions.api.router import get_router as get_inter_router  # type: ignore
    from modules.interactions.config_loader import load_config as load_inter_cfg  # type: ignore
    from modules.interactions.services.engine import InteractionEngine  # type: ignore
    from modules.gateway.url import gateway_url, rewrite_loopback_urls  # type: ignore

    base = str(started.get("gateway_base_url", "http://127.0.0.1:8080"))
    icfg = rewrite_loopback_urls(
        load_inter_cfg(None, overrides=_agent_section("interactions") or None),
        base,
    )
    icfg.setdefault("adapter", {})["http_base_url"] = gateway_url(base, "/neopixel")
    eng = InteractionEngine(
        icfg,
        neo_client=started.get("neopixel"),
        expression_arbiter=started.get("expression_arbiter"),
    )
    if _should_autostart_services():
        eng.start()
    else:
        logger.info("interactions auto-start skipped (autostart disabled)")
    started["interactions"] = eng
    app.include_router(get_inter_router(eng))


def _include_speak(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.gateway.url import gateway_url  # type: ignore
    from modules.speak.xSpeakService import SpeakService  # type: ignore
    from modules.speak.api.router import get_router as get_speak_router  # type: ignore

    base = str(started.get("gateway_base_url", "http://127.0.0.1:8080"))
    svc = SpeakService()
    liveliness = svc.cfg.get("liveliness", {}) if isinstance(svc.cfg.get("liveliness", {}), dict) else {}
    liveliness["interactions_base_url"] = gateway_url(base, "/interactions")
    svc.cfg["liveliness"] = liveliness
    started["speak"] = svc
    app.include_router(get_speak_router(svc))
    logger.info("module speak mounted")


def _include_speech(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.speech.xSpeechService import SpeechService  # type: ignore
    from modules.speech.api import get_router as get_speech_router  # type: ignore
    svc = SpeechService()
    started["speech"] = svc
    try:
        from pathlib import Path

        model_dir = Path(__file__).resolve().parents[2] / "speech" / "models" / "vosk-tr"
        if not model_dir.is_dir():
            logger.error(
                "Vosk TR model missing at %s — speech/STT will not work after wakeword. "
                "Run: python tools/install_vosk_tr.py",
                model_dir,
            )
    except Exception:
        pass
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
    app.include_router(get_speech_router(svc, gateway_base_url=str(started.get("gateway_base_url", ""))))
    logger.info("module speech mounted")


def _include_wakeword(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.gateway.url import gateway_url  # type: ignore
    from modules.wakeword.xWakewordService import WakewordService  # type: ignore
    from modules.wakeword.api import get_router as get_wakeword_router  # type: ignore

    from modules.wakeword.xWakewordService import WakewordActions  # type: ignore

    base = str(started.get("gateway_base_url", "http://127.0.0.1:8080"))
    svc = WakewordService()
    actions = dict(svc.cfg.get("actions", {}) or {})
    actions.update({
        "speech_start_url": gateway_url(base, "/speech/start"),
        "speech_stop_url": gateway_url(base, "/speech/stop"),
        "speak_stop_url": gateway_url(base, "/speak/stop"),
        "agent_interrupt_url": gateway_url(base, "/agent/speech/interrupt"),
        "speech_last_url": gateway_url(base, "/speech/last"),
        "interactions_event_url": gateway_url(base, "/interactions/event"),
    })
    svc.actions = WakewordActions(actions)
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
    from modules.camera.services.imx500_runner import Imx500Config, Imx500Runner  # type: ignore
    from modules.camera.services.onsensor_bus import get_default_bus  # type: ignore
    from modules.camera.api import get_router as get_cam_router  # type: ignore
    ccfg = _merge_with_agent_section(load_cam_cfg(None), "camera")
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
        opencv_max_open_attempts=int(ccfg.get("opencv", {}).get("max_open_attempts", 5)),
        opencv_retry_interval_s=float(ccfg.get("opencv", {}).get("retry_interval_s", 1.0)),
    )
    publisher = FramePublisher()
    capture = CameraCapture(cap_cfg, publisher)
    if _should_autostart_services():
        capture.start()
    else:
        logger.info("camera auto-start skipped (autostart disabled)")
    app.include_router(get_cam_router(capture, cap_cfg.fps_target), prefix="/camera", tags=["camera"])
    started["camera"] = capture
    started["onsensor_bus"] = get_default_bus()

    imx_cfg_raw = ccfg.get("imx500", {}) if isinstance(ccfg.get("imx500", {}), dict) else {}
    imx_cfg = Imx500Config(
        enabled=bool(imx_cfg_raw.get("enabled", False)),
        model_path=str(imx_cfg_raw.get("model_path", "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk")),
        labels_path=str(imx_cfg_raw.get("labels_path", "/usr/share/imx500-models/coco_labels.txt")),
        confidence=float(imx_cfg_raw.get("confidence", 0.45)),
        publish_metadata=bool(imx_cfg_raw.get("publish_metadata", True)),
        publish_interval_s=float(imx_cfg_raw.get("publish_interval_s", 0.05)),
        classes_of_interest=tuple(imx_cfg_raw.get("classes_of_interest", []) or []),
    )
    runner = Imx500Runner(imx_cfg, bus=started["onsensor_bus"], picam=getattr(capture, "_picam", None))
    if imx_cfg.enabled and _should_autostart_services():
        try:
            runner.start()
        except Exception as exc:
            logger.warning("IMX500 runner failed to start: %s", exc)
    started["imx500_runner"] = runner
    logger.info("module camera mounted (imx500_enabled=%s, available=%s)", imx_cfg.enabled, runner.available)


def _include_animate(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.animate.xAnimateService import xAnimateService  # type: ignore
    from modules.animate.api.router import get_router as get_anim_router  # type: ignore
    ardu = started.get("arduino")
    anim_overrides = _agent_section("animate") or None
    if ardu is None:
        logger.warning("animate skipped: arduino module not mounted (no duplicate serial)")
        return
    anim = xAnimateService(serial=ardu, config_overrides=anim_overrides)
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


def _include_autonomy(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.gateway.url import patch_service_endpoints  # type: ignore
    from modules.autonomy.xAutonomyService import xAutonomyService  # type: ignore
    from modules.autonomy.api.router import get_router as get_autonomy_router  # type: ignore

    autonomy_overrides = dict(_agent_section("autonomy") or {})
    endpoints = dict(autonomy_overrides.get("endpoints", {}) or {})
    autonomy_overrides["endpoints"] = patch_service_endpoints(
        endpoints,
        str(started.get("gateway_base_url", "http://127.0.0.1:8080")),
    )
    svc = xAutonomyService(config_overrides=autonomy_overrides)
    if _should_autostart_services():
        svc.start()
    else:
        logger.info("autonomy auto-start skipped (autostart disabled)")
    started["autonomy"] = svc
    app.include_router(get_autonomy_router(svc.brain))
    logger.info("module autonomy mounted")


def _include_agent_core(app: FastAPI, started: Dict[str, object]) -> None:
    """Expose the embedded :class:`AgentOrchestrator` over HTTP.

    The autonomy service constructs its own ``AgentOrchestrator`` instance
    (``brain.agent``); mounting the router here ensures ``/agent/*`` paths
    such as ``/agent/events``, ``/agent/arbiters/stream`` and
    ``/agent/actions/queue`` are reachable from the rest of the system.
    """
    autonomy = started.get("autonomy")
    brain = getattr(autonomy, "brain", None) if autonomy is not None else None
    agent = getattr(brain, "agent", None) if brain is not None else None
    if agent is None:
        logger.info("agent_core mount skipped: no orchestrator found on autonomy.brain.agent")
        return
    from modules.agent_core.api.router import get_router as get_agent_router  # type: ignore

    started["agent_core"] = agent
    app.include_router(get_agent_router(agent))
    logger.info("module agent_core mounted (in-process orchestrator)")


def _include_notifier(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.notifier.config_loader import load_config as load_not_cfg  # type: ignore
    from modules.notifier.api.router import get_router as get_notifier_router  # type: ignore
    from modules.notifier.services.telegram_bot import build_telegram_bot  # type: ignore

    ncfg = _merge_with_agent_section(load_not_cfg(None), "notifier")
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

    svc = xOledFacesService(
        state_store=state_store,
        expression_arbiter=started.get("expression_arbiter"),
    )

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


def _init_gateway_base_url(started: Dict[str, object], cfg: Dict[str, Any]) -> str:
    from modules.gateway.url import resolve_gateway_base_url  # type: ignore

    base = resolve_gateway_base_url(cfg, started=started)
    started["gateway_base_url"] = base
    try:
        from modules.agent_core.services.expression_arbiter import ExpressionArbiter  # type: ignore

        started.setdefault("expression_arbiter", ExpressionArbiter())
    except Exception as exc:
        logger.warning("expression arbiter init skipped: %s", exc)
    return base


_CRITICAL_MODULES = frozenset(
    {"arduino", "camera", "autonomy", "agent_core", "speech", "wakeword", "speak", "ollama"}
)


def bootstrap(app: FastAPI, cfg: Dict[str, Any]) -> Dict[str, object]:
    """Start and wire modules according to cfg.include and return started dict."""
    started: Dict[str, object] = {}
    gateway_base = _init_gateway_base_url(started, cfg)

    include = cfg.get("include", {})

    def _try(fn, name: str = ""):
        try:
            fn()
        except Exception as exc:
            log = logger.error if name in _CRITICAL_MODULES else logger.warning
            log("module %s failed to mount: %s", name or fn.__name__, exc)

    # social_db is the persistence backbone for identity, mood and rituals; mount first.
    if include.get("social_db", True):
        _try(lambda: _include_social_db(app, started), "social_db")

    if include.get("arduino"):
        _try(lambda: _include_arduino(app, started), "arduino")
    if include.get("esp_link"):
        _try(lambda: _include_esp_link(app, started), "esp_link")
    # Camera before VLM so HTTP healthz / MJPEG exist before stream capture starts.
    if include.get("camera"):
        _try(lambda: _include_camera(app, started), "camera")
    if include.get("vlm_bridge"):
        _try(lambda: _include_vlm_bridge(app, started), "vlm_bridge")
    if include.get("neopixel"):
        _try(lambda: _include_neopixel(app, started), "neopixel")
    if include.get("interactions"):
        _try(lambda: _include_interactions(app, started, cfg), "interactions")
    if include.get("speak"):
        _try(lambda: _include_speak(app, started), "speak")
    if include.get("wakeword"):
        _try(lambda: _include_wakeword(app, started), "wakeword")
    if include.get("speech"):
        _try(lambda: _include_speech(app, started), "speech")
    if include.get("ollama"):
        _try(lambda: _include_ollama(app, started), "ollama")
    if include.get("logs"):
        _try(lambda: _include_logs(app, started), "logs")
    if include.get("animate"):
        _try(lambda: _include_animate(app, started), "animate")
    if include.get("piservo"):
        _try(lambda: _include_piservo(app, started), "piservo")
    if include.get("autonomy"):
        _try(lambda: _include_autonomy(app, started), "autonomy")
    if include.get("agent_core", True):
        _try(lambda: _include_agent_core(app, started), "agent_core")

    # optional: mutagen
    if include.get("mutagen"):
        _try(lambda: app.include_router(__import__("modules.mutagen.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.mutagen.config_loader", fromlist=["load_config"]).load_config(None),
                "mutagen",
            )
        )), "mutagen")
        started["mutagen"] = True

    # optional: ota
    if include.get("ota"):
        _try(lambda: app.include_router(__import__("modules.ota.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.ota.config_loader", fromlist=["load_config"]).load_config(None),
                "ota",
            )
        )), "ota")
        started["ota"] = True

    # new optional modules
    if include.get("hardware"):
        _try(lambda: app.include_router(__import__("modules.hardware.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.hardware.config_loader", fromlist=["load_config"]).load_config(None),
                "hardware",
            )
        )), "hardware")
        started["hardware"] = True

    if include.get("telemetry"):
        _try(lambda: app.include_router(__import__("modules.telemetry.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.telemetry.config_loader", fromlist=["load_config"]).load_config(None),
                "telemetry",
            )
        )), "telemetry")
        started["telemetry"] = True

    if include.get("diagnostics"):
        _try(lambda: app.include_router(__import__("modules.diagnostics.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.diagnostics.config_loader", fromlist=["load_config"]).load_config(None),
                "diagnostics",
            )
        )), "diagnostics")
        started["diagnostics"] = True

    if include.get("state_manager"):
        def _mount_state():
            cfg_sm = _merge_with_agent_section(
                __import__("modules.state_manager.config_loader", fromlist=["load_config"]).load_config(None),
                "state_manager",
            )
            StateStore = __import__("modules.state_manager.services.store", fromlist=["StateStore"]).StateStore
            get_router = __import__("modules.state_manager.api.router", fromlist=["get_router"]).get_router
            store = StateStore(
                defaults=cfg_sm.get("defaults", {}),
                persistence=cfg_sm.get("persistence", {}),
            )
            started["state_manager"] = store
            app.include_router(get_router(store))
        _try(_mount_state, "state_manager")

    if include.get("oled_faces"):
        _try(lambda: _include_oled_faces(app, started), "oled_faces")

    if include.get("scheduler"):
        def _mount_scheduler():
            cfg_sc = _merge_with_agent_section(
                __import__("modules.scheduler.config_loader", fromlist=["load_config"]).load_config(None),
                "scheduler",
            )
            Scheduler = __import__("modules.scheduler.services.runner", fromlist=["Scheduler"]).Scheduler
            get_router = __import__("modules.scheduler.api.router", fromlist=["get_router"]).get_router
            gw_base = str(
                cfg_sc.get("gateway_base_url")
                or started.get("gateway_base_url")
                or f"http://127.0.0.1:{int(cfg.get('server', {}).get('port', 8080))}"
            )
            sched = Scheduler(
                jobs=cfg_sc.get("jobs", []),
                gateway_base_url=gw_base,
            )
            if _should_autostart_services():
                sched.start()
            else:
                logger.info("scheduler auto-start skipped (autostart disabled)")
            started["scheduler"] = sched
            app.include_router(get_router(cfg_sc, sched))

        _try(_mount_scheduler, "scheduler")

    if include.get("notifier"):
        _try(lambda: _include_notifier(app, started), "notifier")

    if include.get("calibration"):
        _try(lambda: app.include_router(__import__("modules.calibration.api.router", fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__("modules.calibration.config_loader", fromlist=["load_config"]).load_config(None),
                "calibration",
            )
        )), "calibration")
        started["calibration"] = True

    if include.get("config_center"):
        def _mount_config_center():
            from modules.config_center.config_loader import load_config as load_cc_cfg  # type: ignore
            from modules.config_center.api.router import get_router as get_cc_router  # type: ignore
            from modules.config_center.services import (  # type: ignore
                RuntimeConfigRegistry,
                set_default_registry,
            )

            cc_cfg = _merge_with_agent_section(load_cc_cfg(None), "config_center")
            registry = RuntimeConfigRegistry()
            set_default_registry(registry)
            _register_runtime_keys(registry, started)
            started["runtime_registry"] = registry
            app.include_router(get_cc_router(cc_cfg, registry=registry))

        _try(_mount_config_center, "config_center")
        started["config_center"] = True

    if include.get("admin_ui", True):
        _try(lambda: _include_admin_ui(app, started, cfg), "admin_ui")

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

    # Living Vision wiring: VLM event bus -> Autonomy -> Agent Core events
    vlm_bridge = started.get("vlm_bridge")
    autonomy = started.get("autonomy")
    try:
        brain = getattr(autonomy, "brain", None)
        if vlm_bridge is not None and brain is not None and hasattr(vlm_bridge, "event_bus") and getattr(vlm_bridge, "event_bus", None):
            def _forward_vlm_event(event_type: str, data: Dict[str, Any]) -> None:
                try:
                    if hasattr(brain, "client") and hasattr(brain.client, "emit_agent_event"):
                        brain.client.emit_agent_event(event_type, data)
                except Exception:
                    pass

            vlm_bridge.event_bus.subscribe_all(_forward_vlm_event)
            logger.info("vlm event bus -> agent event bridge mounted")
    except Exception as exc:
        logger.warning("vlm/autonomy event bridge mount failed: %s", exc)

    # On-sensor (IMX500) detections -> VLM processor cache
    bus = started.get("onsensor_bus")
    if vlm_bridge is not None and bus is not None and hasattr(vlm_bridge, "attach_onsensor_bus"):
        try:
            vlm_bridge.attach_onsensor_bus(bus)
            logger.info("onsensor bus -> vlm_bridge subscriber attached")
        except Exception as exc:
            logger.warning("onsensor bus attach failed: %s", exc)

    interactions = started.get("interactions")
    piservo = started.get("piservo")
    if interactions is not None and piservo is not None and hasattr(interactions, "register_event_handler"):
        # Map interaction events onto expressive ear motion. Emotion events keep
        # the ears in sync with eyes/LEDs; sound/vision events add reactive
        # gestures; wakeword keeps its dedicated perk-up gesture.
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

    return started


