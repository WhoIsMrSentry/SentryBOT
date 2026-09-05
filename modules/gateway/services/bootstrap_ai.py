from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI

from .bootstrap_config import (
    _agent_section,
    _camera_hardware_available,
    _merge_with_agent_section,
    _should_autostart_services,
)

logger = logging.getLogger("gateway.bootstrap.ai")


def _include_vlm_bridge(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.vlm_bridge.config_loader import load_config as load_vlm_cfg  # type: ignore
    from modules.vlm_bridge.services.processor import VisionProcessor  # type: ignore
    from modules.vlm_bridge.api.router import get_router as get_vlm_router  # type: ignore

    vcfg = load_vlm_cfg(None)
    processor = VisionProcessor(vcfg)
    cam_hw = _camera_hardware_available(cfg)
    if hasattr(processor, "set_camera_hardware_available"):
        processor.set_camera_hardware_available(cam_hw)
    ardu = started.get("arduino")
    if ardu is not None and hasattr(processor, "set_track_callback") and hasattr(ardu, "track"):

        def _track_callback(head_pan: float, head_tilt: float, drive: int = 0):
            try:
                return ardu.track(head_pan=float(head_pan), head_tilt=float(head_tilt), drive=int(drive))
            except Exception:
                return None

        processor.set_track_callback(_track_callback)

    if _should_autostart_services():
        vision_cfg = vcfg.get("vision", {}) if isinstance(vcfg.get("vision", {}), dict) else {}
        mode = str(vision_cfg.get("processing_mode", "remote")).strip().lower()
        hybrid = bool(vision_cfg.get("hybrid_local_capture", False))
        if cam_hw and (mode == "local" or hybrid):
            try:
                processor.start_stream_processing()
            except Exception as exc:
                logger.warning("vlm_bridge stream start skipped: %s", exc)
        else:
            logger.info("vlm_bridge stream skipped (camera off or remote-only mode)")
    if getattr(processor, "head_arbiter", None) is not None:
        previous = started.get("head_arbiter")
        started["head_arbiter"] = processor.head_arbiter
        # R1 single-instance invariant: when the processor's configured
        # instance becomes the canonical one, rebuild the transport wrapper
        # that still holds the earlier bare instance.
        if previous is not None and previous is not processor.head_arbiter:
            arduino = started.get("arduino")
            if arduino is not None and hasattr(arduino, "set_head_arbiter"):
                try:
                    arduino.set_head_arbiter(processor.head_arbiter)
                    logger.info("head_arbiter single-instance: transport re-bound to processor instance")
                except Exception as exc:
                    logger.warning("head_arbiter transport re-bind failed: %s", exc)
    elif started.get("head_arbiter") is not None:
        processor.head_arbiter = started["head_arbiter"]
    started["vlm_bridge"] = processor
    try:
        app.include_router(
            get_vlm_router(
                processor,
                started.get("arduino"),
                gateway_base_url=str(started.get("gateway_base_url", "")),
            )
        )
    except Exception:
        pass
    logger.info("module vlm_bridge mounted")


def _include_interactions(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.expression.interactions.api.router import get_router as get_inter_router  # type: ignore
    from modules.expression.interactions.config_loader import load_config as load_inter_cfg  # type: ignore
    from modules.expression.interactions.services.engine import InteractionEngine  # type: ignore
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


def _include_expression(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.expression.api.router import get_router as get_expression_router  # type: ignore
    from modules.expression.config_loader import load_config as load_expression_cfg  # type: ignore
    from modules.expression.xExpressionService import xExpressionService  # type: ignore

    ecfg = _merge_with_agent_section(load_expression_cfg(None), "expression")
    adapters = ecfg.setdefault("adapters", {})
    if isinstance(adapters, dict):
        adapters["gateway_url"] = str(started.get("gateway_base_url", "http://127.0.0.1:8080"))
    svc = xExpressionService(config_overrides=ecfg)
    started["expression"] = svc
    router = get_expression_router(svc.engine)
    if hasattr(router, "set_arbiter"):
        router.set_arbiter(svc.arbiter)
    app.include_router(router)

    interactions = started.get("interactions")
    if interactions is not None and hasattr(interactions, "register_event_handler"):
        try:
            interactions.register_event_handler(svc.on_interaction_event)
            logger.info("interactions -> semantic expression state bridge mounted")
        except Exception as exc:
            logger.warning("semantic expression bridge mount failed: %s", exc)

    logger.info("module expression mounted")


def _include_speak(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.gateway.url import gateway_url  # type: ignore
    from modules.voice.speak.xSpeakService import SpeakService  # type: ignore
    from modules.voice.speak.api.router import get_router as get_speak_router  # type: ignore

    base = str(started.get("gateway_base_url", "http://127.0.0.1:8080"))
    svc = SpeakService()
    liveliness = svc.cfg.get("liveliness", {}) if isinstance(svc.cfg.get("liveliness", {}), dict) else {}
    liveliness["interactions_base_url"] = gateway_url(base, "/interactions")
    svc.cfg["liveliness"] = liveliness
    started["speak"] = svc
    app.include_router(get_speak_router(svc))
    logger.info("module speak mounted")


def _include_speech(app: FastAPI, started: Dict[str, object]) -> None:
    import os
    from modules.voice.speech.xSpeechService import SpeechService  # type: ignore
    from modules.voice.speech.api import get_router as get_speech_router  # type: ignore

    svc = SpeechService()
    if started.get("head_arbiter") is not None and hasattr(svc, "attach_head_arbiter"):
        svc.attach_head_arbiter(started["head_arbiter"])
    started["speech"] = svc
    try:
        stt_status = svc.stt_status() if hasattr(svc, "stt_status") else {}
        if not stt_status.get("available", False):
            pc_test = str(os.environ.get("SENTRYBOT_PC_TEST") or os.environ.get("SENTRYBOT_PROFILE") or "").strip().lower() in {
                "1", "true", "yes", "pc", "pc-test", "test"
            }
            message = (
                "Speech/STT unavailable: SpeechRecognition backend error (%s); "
                "speech will not start after wakeword. Ensure 'SpeechRecognition' is installed."
            )
            reason = stt_status.get("reason", "speech_recognition unavailable")
            if pc_test:
                logger.warning("PC TEST: " + message, reason)
            else:
                logger.error(message, reason)
    except Exception as exc:
        logger.debug("speech stt status check failed: %s", exc)

    try:
        from modules.gateway import config_loader as _gw_cfg  # type: ignore

        gwcfg = _gw_cfg.load_config(None)
        speech_cfg = _merge_with_agent_section(gwcfg.get("speech", {}), "speech")
        if bool(speech_cfg.get("listening", False)) or bool(speech_cfg.get("auto_start", False)):
            if _should_autostart_services():
                try:
                    svc.start_background()
                    logger.info("speech listening auto-started on boot")
                except Exception as exc:
                    logger.warning("speech auto-start failed: %s", exc)
    except Exception:
        pass
    app.include_router(get_speech_router(svc, gateway_base_url=str(started.get("gateway_base_url", ""))))
    logger.info("module speech mounted")


def _include_wakeword(app: FastAPI, started: Dict[str, object]) -> None:
    # sentrybot_batch06c_no_hardware_wakeword_stub
    import os as _sentrybot_batch06c_os

    if (
        str(_sentrybot_batch06c_os.getenv("SENTRYBOT_NO_HARDWARE", "")).lower() in {"1", "true", "yes", "on"}
        or str(_sentrybot_batch06c_os.getenv("SENTRYBOT_SKIP_WAKEWORD_AUTOSTART", "")).lower() in {"1", "true", "yes", "on"}
    ):
        _started = locals().get("started") or locals().get("started_services")

        if isinstance(_started, dict):
            _started["wakeword"] = {
                "kind": "stub",
                "available": False,
                "skipped": True,
                "reason": "hardware_disabled",
            }
            _started["wakeword_handle"] = None

        try:
            logger.info("module wakeword mounted as no-hardware stub")
        except Exception:
            pass

        return

    from modules.gateway.url import gateway_url  # type: ignore
    from modules.voice.wakeword.xWakewordService import WakewordService, WakewordActions  # type: ignore
    from modules.voice.wakeword.api import get_router as get_wakeword_router  # type: ignore

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
    from modules.ai_provider.api.router import get_router as get_ollama_router  # type: ignore

    # Try to load with new ai_provider section, fallback to old ollama section for backward compatibility
    try:
        from modules.common.config_loader import load_ai_provider_config as load_ai_provider_cfg  # type: ignore
        ocfg = load_ai_provider_cfg(None)
    except KeyError:
        # Backward compatibility: try loading with old ollama section
        from modules.ai_provider.config_loader import load_config as load_ollama_cfg  # type: ignore
        ocfg = load_ollama_cfg(None)
    app.include_router(get_ollama_router(ocfg))
    started["ollama"] = True
    logger.info("module ollama mounted")


def _include_animate(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.expression.animate.xAnimateService import xAnimateService  # type: ignore
    from modules.expression.animate.api.router import get_router as get_anim_router  # type: ignore

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


def _autonomy_auto_start_enabled(autocfg: Dict[str, Any]) -> bool:
    """Return whether Gateway should start the AutonomyBrain loop on boot."""
    if not _should_autostart_services():
        return False

    if not isinstance(autocfg, dict):
        return True

    # Accept a few aliases so older configs can opt in/out without code changes.
    for key in ("auto_start", "autostart", "start_on_gateway_boot", "gateway_auto_start"):
        if key in autocfg:
            return bool(autocfg.get(key))

    runtime_cfg = autocfg.get("runtime", {}) if isinstance(autocfg.get("runtime"), dict) else {}
    for key in ("auto_start", "autostart", "start_on_gateway_boot", "gateway_auto_start"):
        if key in runtime_cfg:
            return bool(runtime_cfg.get(key))

    gateway_cfg = autocfg.get("gateway", {}) if isinstance(autocfg.get("gateway"), dict) else {}
    for key in ("auto_start", "autostart", "start_on_boot"):
        if key in gateway_cfg:
            return bool(gateway_cfg.get(key))

    # Match other Gateway-mounted services: auto-start unless global autostart is disabled.
    return True


def _include_autonomy(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.autonomy.config_loader import load_config as load_autonomy_cfg  # type: ignore
    from modules.autonomy.xAutonomyService import xAutonomyService  # type: ignore
    from modules.autonomy.api.router import get_router as get_autonomy_router  # type: ignore

    autocfg = _merge_with_agent_section(load_autonomy_cfg(None), "autonomy")
    svc = xAutonomyService(config_overrides=autocfg)
    started["autonomy"] = svc
    app.include_router(get_autonomy_router(svc))

    if _autonomy_auto_start_enabled(autocfg):
        try:
            svc.start()
            started["autonomy_started"] = True
            logger.info("module autonomy mounted and auto-started")
        except Exception as exc:
            started["autonomy_started"] = False
            logger.warning("autonomy auto-start failed: %s", exc)
    else:
        started["autonomy_started"] = False
        logger.info("module autonomy mounted (auto-start disabled)")


def _include_agent_core(app: FastAPI, started: Dict[str, object]) -> None:
    autonomy = started.get("autonomy")
    brain = getattr(autonomy, "brain", None) if autonomy is not None else None
    agent = getattr(brain, "agent", None) if brain is not None else None
    if agent is None:
        logger.info("agent_core mount skipped: no orchestrator found on autonomy.brain.agent")
        return
    from modules.agent_core.api.router import get_router as get_agent_router  # type: ignore

    started["agent_core"] = agent
    app.include_router(get_agent_router(agent))
    logger.info("module agent_core mounted")


def _include_oled_faces(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.visual_output.oled_faces.config_loader import load_config as load_oled_cfg  # type: ignore
    from modules.visual_output.oled_faces.xOledFacesService import xOledFacesService  # type: ignore
    from modules.visual_output.oled_faces.api.router import get_router as get_oled_faces_router  # type: ignore

    ocfg = _merge_with_agent_section(load_oled_cfg(None), "oled_faces")
    from modules.common.led_write_policy import get_shared_policy  # type: ignore

    svc = xOledFacesService(config_overrides=ocfg, expression_arbiter=get_shared_policy())
    try:
        svc.start()
    except Exception as exc:
        logger.warning("oled_faces failed to start, running degraded: %s", exc)

    started["oled_faces"] = svc
    app.include_router(get_oled_faces_router(svc))
    logger.info("module oled_faces mounted")


def _wire_head_arbiter(started: Dict[str, object]) -> None:
    arbiter = started.get("head_arbiter")
    if arbiter is None:
        return
    speech = started.get("speech")
    if speech is not None and hasattr(speech, "attach_head_arbiter"):
        try:
            speech.attach_head_arbiter(arbiter)
            logger.info("head_arbiter wired to speech service")
        except Exception as exc:
            logger.debug("speech head_arbiter attach skipped: %s", exc)
    autonomy = started.get("autonomy")
    brain = getattr(autonomy, "brain", None) if autonomy is not None else None
    client = getattr(brain, "client", None) if brain is not None else None
    if client is not None and hasattr(client, "attach_head_arbiter"):
        try:
            client.attach_head_arbiter(arbiter)
            logger.info("head_arbiter wired to autonomy client")
        except Exception as exc:
            logger.debug("autonomy head_arbiter attach skipped: %s", exc)


def _wire_wakeword_interactions(started: Dict[str, object]) -> None:
    wakeword = started.get("wakeword")
    if wakeword is None:
        return
    actions = getattr(wakeword, "actions", None)
    if actions is not None:
        if started.get("interactions") is not None:
            actions._interactions_engine = started.get("interactions")
        if started.get("speech") is not None:
            actions._speech_service = started.get("speech")
        if started.get("speak") is not None:
            actions._speak_service = started.get("speak")
        if started.get("agent_core") is not None:
            actions._agent_service = started.get("agent_core")
        logger.info("wakeword wired to speech/speak/agent/interactions engines (in-process 0ms barge-in)")


def _wire_speech_interactions(started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    interactions = started.get("interactions")
    if interactions is None:
        return
    try:
        from modules.voice.speech.api.router import set_interactions_engine  # type: ignore

        set_interactions_engine(interactions)
        logger.info("speech wired to interactions engine (in-process events)")
    except Exception as exc:
        logger.debug("speech interactions wiring skipped: %s", exc)


def _wire_vlm_autonomy(started: Dict[str, object]) -> None:
    vlm_bridge = started.get("vlm_bridge")
    autonomy = started.get("autonomy")
    try:
        brain = getattr(autonomy, "brain", None)
        if (
            vlm_bridge is not None
            and brain is not None
            and hasattr(vlm_bridge, "event_bus")
            and getattr(vlm_bridge, "event_bus", None)
        ):

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
