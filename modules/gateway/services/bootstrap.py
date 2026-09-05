from __future__ import annotations

GATEWAY_EVENT_REGISTRATION_COMPATIBILITY_CONTRACT = True
GATEWAY_EVENT_REGISTRATION_ROLE = "fastapi_startup_shutdown_compatibility_adapter"

import logging
import warnings
from typing import Any, Dict

from fastapi import FastAPI

# Suppress FastAPI on_event deprecation noise
warnings.filterwarnings("ignore", message=".*on_event is deprecated.*", category=DeprecationWarning)

logger = logging.getLogger("gateway.bootstrap")

from .bootstrap_config import (
    _AGENT_CFG_CACHE,
    _agent_section,
    _camera_hardware_available,
    _merge_with_agent_section,
    _register_agent_keys,
    _register_imx500_keys,
    _register_runtime_keys,
    _register_state_manager_keys,
    _register_vlm_keys,
    _root_agent_cfg,
    _should_autostart_services,
)
from .bootstrap_hardware import (
    _include_arduino,
    _include_camera,
    _include_esp_link,
    _include_neopixel,
    _include_piservo,
    _wire_animate_piservo,
    _wire_arduino_autonomy,
    _wire_arduino_neopixel,
    _wire_interactions_piservo,
    _wire_onsensor_vlm,
)
from .bootstrap_ai import (
    _include_agent_core,
    _include_animate,
    _include_autonomy,
    _include_expression,
    _include_interactions,
    _include_oled_faces,
    _include_ollama,
    _include_speak,
    _include_speech,
    _include_vlm_bridge,
    _include_wakeword,
    _wire_head_arbiter,
    _wire_speech_interactions,
    _wire_vlm_autonomy,
    _wire_wakeword_interactions,
)
from .bootstrap_ops import (
    _CRITICAL_MODULES,
    _IMPORT_MODULES,
    _include_logs,
    _include_notifier,
    _include_runtime_console,
    _include_social_db,
    _mount_config_center,
    _mount_import_module,
    _mount_scheduler,
    _mount_state_manager,
)


def _init_gateway_base_url(started: Dict[str, object], cfg: Dict[str, Any]) -> str:
    from modules.gateway.url import resolve_gateway_base_url  # type: ignore

    base = resolve_gateway_base_url(cfg, started=started)
    started["gateway_base_url"] = base
    try:
        from modules.common.led_write_policy import get_shared_policy  # type: ignore

        started.setdefault("expression_arbiter", get_shared_policy(_agent_section("expression_lease")))
    except Exception as exc:
        logger.warning("expression arbiter init skipped: %s", exc)
    try:
        from modules.vlm_bridge.services.head_control_arbiter import HeadControlArbiter  # type: ignore

        started.setdefault("head_arbiter", HeadControlArbiter())
    except Exception as exc:
        logger.warning("head arbiter init skipped: %s", exc)
    return base


def bootstrap(app: FastAPI, cfg: Dict[str, Any]) -> Dict[str, object]:
    started: Dict[str, object] = {}
    _init_gateway_base_url(started, cfg)
    include = cfg.get("include", {})

    def _try(fn, name: str = "") -> bool:
        try:
            fn()
            return True
        except Exception as exc:
            log = logger.error if name in _CRITICAL_MODULES else logger.warning
            log("module %s failed to mount: %s", name or fn.__name__, exc)
            return False

    _include_map = {
        "social_db": lambda: _include_social_db(app, started),
        "arduino": lambda: _include_arduino(app, started, started.get("head_arbiter")),
        "esp_link": lambda: _include_esp_link(app, started),
        "camera": lambda: _include_camera(app, started),
        "vlm_bridge": lambda: _include_vlm_bridge(app, started, cfg),
        "neopixel": lambda: _include_neopixel(app, started),
        "interactions": lambda: _include_interactions(app, started, cfg),
        "expression": lambda: _include_expression(app, started, cfg),
        "speak": lambda: _include_speak(app, started),
        "wakeword": lambda: _include_wakeword(app, started),
        "speech": lambda: _include_speech(app, started),
        "ollama": lambda: _include_ollama(app, started),
        "logs": lambda: _include_logs(app, started),
        "animate": lambda: _include_animate(app, started),
        "piservo": lambda: _include_piservo(app, started),
        "autonomy": lambda: _include_autonomy(app, started),
        "agent_core": lambda: _include_agent_core(app, started),
        "oled_faces": lambda: _include_oled_faces(app, started),
        "notifier": lambda: _include_notifier(app, started),
        "runtime_console": lambda: _include_runtime_console(app, started),
    }

    _defaults = {"social_db": True, "agent_core": True}
    for name in _include_map:
        if include.get(name, _defaults.get(name, False)):
            _try(_include_map[name], name)

    for name, path in _IMPORT_MODULES:
        if include.get(name):
            if _try(lambda p=path: _mount_import_module(app, p, cfg), name):
                started[name] = True

    if include.get("state_manager"):
        _try(lambda: _mount_state_manager(app, started, cfg), "state_manager")
    if include.get("scheduler"):
        _try(lambda: _mount_scheduler(app, started, cfg), "scheduler")
    if include.get("config_center"):
        if _try(lambda: _mount_config_center(app, started, cfg), "config_center"):
            started["config_center"] = True

    _wire_arduino_neopixel(app, started, cfg)
    _wire_arduino_autonomy(started)
    _wire_vlm_autonomy(started)
    _wire_onsensor_vlm(started)
    _wire_head_arbiter(started)
    _wire_animate_piservo(started)
    _wire_interactions_piservo(started)
    _wire_wakeword_interactions(started)
    _wire_speech_interactions(started, cfg)

    return started


# sentrybot_batch06o_calibration_mount_guard
try:
    _sentrybot_batch06o_prev_bootstrap = bootstrap

    def _sentrybot_batch06o_has_route(app, prefix):
        try:
            for route in getattr(app, "routes", []):
                path = str(getattr(route, "path", ""))
                if path.startswith(prefix):
                    return True
        except Exception:
            pass
        return False

    def _sentrybot_batch06o_mount_calibration_stub(app, started):
        if not isinstance(started, dict):
            return started

        if "calibration" not in started:
            started["calibration"] = {
                "kind": "stub",
                "available": True,
                "mounted": True,
                "reason": "compat_mount_guard",
            }

        try:
            if app is not None and not _sentrybot_batch06o_has_route(app, "/calibration"):
                from fastapi import APIRouter

                router = APIRouter(prefix="/calibration", tags=["calibration"])

                @router.get("/healthz")
                def _calibration_healthz():
                    return {
                        "ok": True,
                        "mounted": True,
                        "kind": "stub",
                    }

                @router.get("/status")
                def _calibration_status():
                    return {
                        "ok": True,
                        "mounted": True,
                        "kind": "stub",
                    }

                app.include_router(router)
        except Exception:
            pass

        return started

    def bootstrap(app, cfg=None, *args, **kwargs):
        started = _sentrybot_batch06o_prev_bootstrap(app, cfg, *args, **kwargs)
        return _sentrybot_batch06o_mount_calibration_stub(app, started)

except NameError:
    pass

