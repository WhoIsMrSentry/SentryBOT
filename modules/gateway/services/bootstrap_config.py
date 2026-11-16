from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("gateway.bootstrap.config")

_AGENT_CFG_LOCK = threading.RLock()
_AGENT_CFG_CACHE: Optional[Dict[str, Any]] = None
_AGENT_CFG_META: Optional[Tuple[str, Optional[int]]] = None


def invalidate_agent_cfg_cache() -> None:
    """Clear gateway cached root agent.yaml configuration."""
    with _AGENT_CFG_LOCK:
        global _AGENT_CFG_CACHE, _AGENT_CFG_META
        _AGENT_CFG_CACHE = None
        _AGENT_CFG_META = None
    try:
        from modules.common.config_loader import clear_agent_config_cache  # type: ignore

        clear_agent_config_cache()
    except Exception:
        pass


def _agent_cfg_signature() -> Tuple[str, Optional[int]]:
    try:
        from modules.common.config_loader import resolve_agent_cfg_path  # type: ignore

        path = resolve_agent_cfg_path(None)
        return str(path), path.stat().st_mtime_ns
    except Exception:
        return "", None


def _root_agent_cfg() -> Dict[str, Any]:
    global _AGENT_CFG_CACHE, _AGENT_CFG_META
    sig = _agent_cfg_signature()
    with _AGENT_CFG_LOCK:
        if _AGENT_CFG_CACHE is not None and _AGENT_CFG_META == sig:
            return _AGENT_CFG_CACHE
        if _AGENT_CFG_META is not None and _AGENT_CFG_META != sig:
            try:
                from modules.common.config_loader import clear_agent_config_cache  # type: ignore

                clear_agent_config_cache()
            except Exception:
                pass
        try:
            from modules.common.config_loader import load_agent_config  # type: ignore

            cfg = load_agent_config(None)
            _AGENT_CFG_CACHE = cfg if isinstance(cfg, dict) else {}
        except Exception:
            _AGENT_CFG_CACHE = {}
        _AGENT_CFG_META = sig
        return _AGENT_CFG_CACHE


def mount_module_stub(
    app: Any,
    started: Dict[str, object],
    name: str,
    *,
    prefix: Optional[str] = None,
    reason: str = "hardware_disabled",
    mount_routes: bool = True,
    extra_started: Optional[Dict[str, object]] = None,
) -> Dict[str, Any]:
    """Register a unified offline/stub entry in ``started`` and optionally mount healthz/status routes."""
    stub_state: Dict[str, Any] = {
        "kind": "stub",
        "available": False,
        "skipped": True,
        "reason": reason,
    }
    if isinstance(started, dict):
        started[name] = stub_state
        if extra_started:
            started.update(extra_started)

    if mount_routes and app is not None and prefix:
        norm_prefix = "/" + prefix.strip("/")
        already = any(str(getattr(r, "path", "")).startswith(norm_prefix) for r in getattr(app, "routes", []))
        if not already:
            try:
                from fastapi import APIRouter

                router = APIRouter(prefix=norm_prefix, tags=[name])

                @router.get("/healthz")
                def _stub_healthz() -> Dict[str, Any]:
                    return {"ok": True, "available": False, "skipped": True, "reason": reason}

                @router.get("/status")
                def _stub_status() -> Dict[str, Any]:
                    return {"ok": True, "available": False, "skipped": True, "reason": reason}

                app.include_router(router)
            except Exception as exc:
                logger.debug("stub route mount failed for %s: %s", name, exc)

    return stub_state


def _agent_section(name: str) -> Dict[str, Any]:
    cfg = _root_agent_cfg()
    value = cfg.get(name, {}) if isinstance(cfg, dict) else {}
    return value if isinstance(value, dict) else {}


def _merge_with_agent_section(base_cfg: Dict[str, Any], section_name: str) -> Dict[str, Any]:
    section = _agent_section(section_name)
    if not section:
        return base_cfg
    try:
        from modules.common.config_loader import deep_merge  # type: ignore

        return deep_merge(base_cfg, section)
    except Exception:
        merged = dict(base_cfg)
        merged.update(section)
        return merged


def _camera_hardware_available(cfg: Dict[str, Any]) -> bool:
    """True only when gateway mounts camera AND merged config has enabled=true."""
    include = cfg.get("include", {}) if isinstance(cfg.get("include"), dict) else {}
    if not include.get("camera"):
        return False
    try:
        from modules.camera.config_loader import load_config as load_cam_cfg  # type: ignore

        cam_section = _merge_with_agent_section(load_cam_cfg(None), "camera")
        return bool(cam_section.get("enabled", False))
    except Exception:
        return False


def _should_autostart_services() -> bool:
    """Disable heavy background starts unless explicitly enabled."""
    force = str(os.getenv("SENTRYBOT_FORCE_AUTOSTART", "")).strip().lower()
    if force in {"1", "true", "yes", "on"}:
        return True

    disable = str(os.getenv("SENTRYBOT_DISABLE_AUTOSTART", "")).strip().lower()
    if disable in {"1", "true", "yes", "on"}:
        return False

    return not bool(os.getenv("PYTEST_CURRENT_TEST"))


def _register_vlm_keys(registry: Any, vlm_bridge: Any) -> None:
    if vlm_bridge is None or not hasattr(vlm_bridge, "get_modes"):
        return

    def _vlm_apply_mode(key: str):
        def _apply(value: Any) -> Optional[Dict[str, Any]]:
            if vlm_bridge is None or not hasattr(vlm_bridge, "set_modes"):
                return None
            return vlm_bridge.set_modes({key: bool(value)})

        return _apply

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


def _register_agent_keys(registry: Any, agent: Any) -> None:
    if agent is None:
        return

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


def _register_imx500_keys(registry: Any, imx_runner: Any) -> None:
    if imx_runner is None:
        return

    def _apply_imx500_enabled(value: Any) -> Optional[Dict[str, Any]]:
        try:
            imx_runner.cfg.enabled = bool(value)
            if imx_runner.cfg.enabled:
                started = bool(imx_runner.start())
                return {"ok": started, "enabled": True, "status": imx_runner.status()}
            imx_runner.stop()
            return {"ok": True, "enabled": False, "status": imx_runner.status()}
        except Exception as exc:
            logger.warning("IMX500 hot toggle failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _apply_imx500_conf(value: Any) -> Optional[Dict[str, Any]]:
        try:
            imx_runner.cfg.confidence = float(value)
            return {"ok": True, "confidence": imx_runner.cfg.confidence}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    registry.register(
        "camera",
        "imx500.enabled",
        type="bool",
        default=bool(getattr(getattr(imx_runner, "cfg", None), "enabled", False)),
        description="Toggle IMX500 on-sensor inference.",
        apply_fn=_apply_imx500_enabled,
    )
    registry.register(
        "camera",
        "imx500.confidence",
        type="float",
        default=float(getattr(getattr(imx_runner, "cfg", None), "confidence", 0.50)),
        minimum=0.05,
        maximum=1.0,
        description="IMX500 object detection confidence threshold.",
        apply_fn=_apply_imx500_conf,
    )


def _register_state_manager_keys(registry: Any, state_manager: Any) -> None:
    if state_manager is None or not hasattr(state_manager, "set_operational"):
        return

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


def _register_runtime_keys(registry: Any, started: Dict[str, object]) -> None:
    vlm_bridge = started.get("vlm_bridge")
    autonomy = started.get("autonomy")
    agent = getattr(getattr(autonomy, "brain", None), "agent", None) if autonomy is not None else None

    _register_vlm_keys(registry, vlm_bridge)
    _register_agent_keys(registry, agent)
    _register_imx500_keys(registry, started.get("imx500_runner"))
    _register_state_manager_keys(registry, started.get("state_manager"))
