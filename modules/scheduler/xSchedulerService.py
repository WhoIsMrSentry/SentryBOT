from __future__ import annotations
from fastapi import FastAPI
import asyncio

from .config_loader import load_config
from .api.router import get_router
from .services.runner import Scheduler


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    sched = Scheduler(
        jobs=cfg.get("jobs", []),
        gateway_base_url=str(cfg.get("gateway_base_url", "http://127.0.0.1:8080")),
    )

    app = FastAPI(title="Scheduler Service")
    app.include_router(get_router(cfg, sched))

    @app.on_event("startup")
    async def _startup():
        sched.start()

    @app.on_event("shutdown")
    async def _shutdown():
        await sched.stop()

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config(None)
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
