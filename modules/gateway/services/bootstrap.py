from __future__ import annotations

import logging
import time
import warnings
from typing import Any, Dict

from fastapi import FastAPI

from .bootstrap_config import (  # noqa: F401
    _agent_section,
    _camera_hardware_available,
    _merge_with_agent_section,
    _register_agent_keys,
    _register_imx500_keys,
    _register_runtime_keys,
    _register_state_manager_keys,
    _register_vlm_keys,
    _should_autostart_services,
    mount_module_stub,
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
    _include_mcp_client,
    _include_mcp_server,
    _include_oled_faces,
    _include_ollama,
    _include_speak,
    _include_speaker_id,
    _include_speech,
    _include_vlm_bridge,
    _include_wakeword,
    _wire_head_arbiter,
    _wire_speech_interactions,
    _wire_vlm_autonomy,
    _wire_wakeword_interactions,
    _wire_multimodal_identity,
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

GATEWAY_EVENT_REGISTRATION_COMPATIBILITY_CONTRACT = True
GATEWAY_EVENT_REGISTRATION_ROLE = "fastapi_startup_shutdown_compatibility_adapter"

# Suppress FastAPI on_event deprecation noise
warnings.filterwarnings("ignore", message=".*on_event is deprecated.*", category=DeprecationWarning)

logger = logging.getLogger("gateway.bootstrap")


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


def _mount_calibration_stub(app: FastAPI, started: Dict[str, object]) -> Dict[str, object]:
    if isinstance(started, dict) and "calibration" not in started:
        mount_module_stub(
            app,
            started,
            "calibration",
            prefix="/calibration",
            reason="compat_mount_guard",
        )
    return started


def bootstrap(app: FastAPI, cfg: Dict[str, Any] | None = None) -> Dict[str, object]:
    boot_t0 = time.perf_counter()
    cfg = cfg if isinstance(cfg, dict) else {}
    started: Dict[str, object] = {}
    boot_manifest: list[Dict[str, Any]] = []
    _init_gateway_base_url(started, cfg)
    include = cfg.get("include", {}) if isinstance(cfg.get("include"), dict) else {}

    def _module_status(name: str) -> tuple[str, str]:
        val = started.get(name)
        if val is None:
            return "skipped", "not_mounted"
        if isinstance(val, dict) and val.get("kind") == "stub":
            return "stub", str(val.get("reason", "stub"))
        return "active", "ok"

    def _try(fn, name: str = "") -> bool:
        t0 = time.perf_counter()
        try:
            fn()
            dur = round((time.perf_counter() - t0) * 1000.0, 2)
            status, reason = _module_status(name)
            boot_manifest.append(
                {"module": name, "status": status, "duration_ms": dur, "reason": reason}
            )
            return True
        except Exception as exc:
            dur = round((time.perf_counter() - t0) * 1000.0, 2)
            log = logger.error if name in _CRITICAL_MODULES else logger.warning
            log("module %s failed to mount: %s", name or fn.__name__, exc)
            boot_manifest.append(
                {"module": name, "status": "error", "duration_ms": dur, "reason": str(exc)}
            )
            return False

    def _record_disabled(name: str) -> None:
        boot_manifest.append(
            {"module": name, "status": "disabled", "duration_ms": 0.0, "reason": "config_disabled"}
        )

    if include.get("state_manager"):
        _try(lambda: _mount_state_manager(app, started, cfg), "state_manager")
    else:
        _record_disabled("state_manager")

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
        "speaker_id": lambda: _include_speaker_id(app, started),
        "ollama": lambda: _include_ollama(app, started),
        "logs": lambda: _include_logs(app, started),
        "animate": lambda: _include_animate(app, started),
        "piservo": lambda: _include_piservo(app, started),
        "autonomy": lambda: _include_autonomy(app, started),
        "agent_core": lambda: _include_agent_core(app, started),
        "oled_faces": lambda: _include_oled_faces(app, started),
        "mcp_client": lambda: _include_mcp_client(app, started),
        "mcp_server": lambda: _include_mcp_server(app, started),
        "notifier": lambda: _include_notifier(app, started),
        "runtime_console": lambda: _include_runtime_console(app, started),
    }

    _defaults = {"social_db": True, "agent_core": True, "speaker_id": True}
    for name in _include_map:
        if include.get(name, _defaults.get(name, False)):
            _try(_include_map[name], name)
        else:
            _record_disabled(name)

    for name, path in _IMPORT_MODULES:
        if include.get(name):
            def _mount_imp(p: str = path, mod: str = name) -> None:
                _mount_import_module(app, p, cfg)
                started[mod] = {"kind": "router", "mounted": True, "ok": True}

            _try(_mount_imp, name)
        else:
            _record_disabled(name)

    if include.get("scheduler"):
        _try(lambda: _mount_scheduler(app, started, cfg), "scheduler")
    else:
        _record_disabled("scheduler")

    if include.get("config_center"):
        def _mount_cc() -> None:
            _mount_config_center(app, started, cfg)
            started["config_center"] = {"kind": "router", "mounted": True, "ok": True}

        _try(_mount_cc, "config_center")
    else:
        _record_disabled("config_center")

    _wire_arduino_neopixel(app, started, cfg)
    _wire_arduino_autonomy(started)
    _wire_vlm_autonomy(started)
    _wire_onsensor_vlm(started)
    _wire_head_arbiter(started)
    _wire_animate_piservo(started)
    _wire_interactions_piservo(started)
    _wire_wakeword_interactions(started)
    _wire_speech_interactions(started, cfg)
    _wire_multimodal_identity(started)

    if include.get("calibration", True):
        _try(lambda: _mount_calibration_stub(app, started), "calibration")
    else:
        _record_disabled("calibration")

    started["_boot_manifest"] = boot_manifest
    started["_boot_total_ms"] = round((time.perf_counter() - boot_t0) * 1000.0, 2)
    return started

