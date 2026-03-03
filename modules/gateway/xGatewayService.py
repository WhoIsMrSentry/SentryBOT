from __future__ import annotations
import logging
from fastapi import FastAPI
from .config_loader import load_config

logger = logging.getLogger("gateway.service")

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception as exc:
    logger.debug("global logging init skipped: %s", exc)


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    app = FastAPI(title="SentryBOT Gateway")

    # state: started services
    app.state.started = {}  # type: ignore[attr-defined]

    # mount/include modules
    try:
        from .services.bootstrap import bootstrap  # type: ignore
        started = bootstrap(app, cfg)
        app.state.started = started  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("gateway bootstrap failed: %s", exc)

    # core API for status/health
    try:
        from .api.router import get_router as get_core_router  # type: ignore
        app.include_router(get_core_router(cfg, app.state.started))  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("gateway core router mount failed: %s", exc)

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
