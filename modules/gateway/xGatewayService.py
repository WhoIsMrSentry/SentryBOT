from __future__ import annotations
from fastapi import FastAPI
from .config_loader import load_config

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


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
    except Exception:
        pass

    # core API for status/health
    try:
        from .api.router import get_router as get_core_router  # type: ignore
        app.include_router(get_core_router(cfg, app.state.started))  # type: ignore[attr-defined]
    except Exception:
        pass

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
