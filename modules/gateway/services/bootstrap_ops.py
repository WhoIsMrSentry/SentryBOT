from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI

from .bootstrap_config import (
    _merge_with_agent_section,
    _register_runtime_keys,
    _should_autostart_services,
)

logger = logging.getLogger("gateway.bootstrap.ops")

_CRITICAL_MODULES = frozenset(
    {"arduino", "camera", "autonomy", "agent_core", "speech", "wakeword", "speak", "ollama"}
)

_IMPORT_MODULES: list[tuple[str, str]] = [
    ("telemetry", "system_control.telemetry"),
    ("diagnostics", "system_control.diagnostics"),
]


def _include_social_db(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.cognitive_memory.config_loader import load_config as load_social_cfg  # type: ignore
    from modules.cognitive_memory.db import SocialDB, set_default  # type: ignore

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


def _include_logs(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.runtime_console.logwrapper import get_router as get_logs_router  # type: ignore

    logs_router = get_logs_router()
    if logs_router is not None:
        app.include_router(logs_router)
        started["logs"] = True
        logger.info("module logs mounted")


def _include_notifier(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.system_control.notifier.config_loader import load_config as load_not_cfg  # type: ignore
    from modules.system_control.notifier.api.router import get_router as get_notifier_router  # type: ignore
    from modules.system_control.notifier.services.telegram_bot import build_telegram_bot  # type: ignore

    ncfg = _merge_with_agent_section(load_not_cfg(None), "notifier")
    bot = build_telegram_bot(ncfg)
    app.include_router(get_notifier_router(ncfg, bot))
    polling_enabled = ncfg.get("telegram", {}).get("polling", {}).get("enabled", False)
    started["notifier"] = True
    if bot and polling_enabled:
        # Single ownership (R48): gateway lifespan starts/stops the bot;
        # no duplicate add_event_handler registration here.
        started["notifier_bot"] = bot
        started["notifier_polling_enabled"] = True
        logger.info("module notifier mounted (polling owned by gateway lifespan)")
    else:
        logger.info("module notifier mounted")


def _include_runtime_console(app: FastAPI, started: Dict[str, object]) -> None:
    from modules.runtime_console.api.router import router as console_router  # type: ignore

    app.include_router(console_router)
    started["runtime_console"] = True
    logger.info("module runtime_console mounted")


def _mount_import_module(app: FastAPI, name: str, cfg: Dict[str, Any]) -> None:
    router_path = f"modules.{name}.api.router"
    config_path = f"modules.{name}.config_loader"
    app.include_router(
        __import__(router_path, fromlist=["get_router"]).get_router(
            _merge_with_agent_section(
                __import__(config_path, fromlist=["load_config"]).load_config(None),
                name,
            )
        )
    )


def _mount_state_manager(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    cfg_sm = _merge_with_agent_section(
        __import__("modules.system_control.state_manager.config_loader", fromlist=["load_config"]).load_config(None),
        "state_manager",
    )
    StateStore = __import__("modules.system_control.state_manager.services.store", fromlist=["StateStore"]).StateStore
    get_router = __import__("modules.system_control.state_manager.api.router", fromlist=["get_router"]).get_router
    store = StateStore(
        defaults=cfg_sm.get("defaults", {}),
        persistence=cfg_sm.get("persistence", {}),
        pubsub=cfg_sm.get("pubsub", {}),
    )
    started["state_manager"] = store
    app.include_router(get_router(store))


def _mount_scheduler(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    cfg_sc = _merge_with_agent_section(
        __import__("modules.system_control.scheduler.config_loader", fromlist=["load_config"]).load_config(None),
        "scheduler",
    )
    Scheduler = __import__("modules.system_control.scheduler.services.runner", fromlist=["Scheduler"]).Scheduler
    get_router = __import__("modules.system_control.scheduler.api.router", fromlist=["get_router"]).get_router
    gw_base = str(
        cfg_sc.get("gateway_base_url")
        or started.get("gateway_base_url")
        or f"http://127.0.0.1:{int(cfg.get('server', {}).get('port', 8080))}"
    )
    sched = Scheduler(
        jobs=cfg_sc.get("jobs", []),
        gateway_base_url=gw_base,
        # Hand in-process services to job handlers when already mounted;
        # handlers fall back to gateway HTTP for anything missing.
        services={
            k: started[k]
            for k in ("speak", "interactions", "diagnostics", "state_manager")
            if started.get(k) is not None
        },
    )
    if _should_autostart_services():
        sched.start()
    else:
        logger.info("scheduler auto-start skipped (autostart disabled)")
    started["scheduler"] = sched
    app.include_router(get_router(cfg_sc, sched))


def _mount_config_center(app: FastAPI, started: Dict[str, object], cfg: Dict[str, Any]) -> None:
    from modules.system_control.config_center.config_loader import load_config as load_cc_cfg
    from modules.system_control.config_center.api.router import get_router as get_cc_router
    from modules.system_control.config_center.services import RuntimeConfigRegistry, set_default_registry

    cc_cfg = _merge_with_agent_section(load_cc_cfg(None), "config_center")
    registry = RuntimeConfigRegistry()
    set_default_registry(registry)
    _register_runtime_keys(registry, started)
    started["runtime_registry"] = registry
    app.include_router(get_cc_router(cc_cfg, registry=registry))
