from __future__ import annotations
from fastapi import FastAPI
import asyncio

from .config_loader import load_config
from .api.router import get_router
from .services.runner import Scheduler


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    app = FastAPI(title="Scheduler Service")
    app.include_router(get_router(cfg))

    sched = Scheduler(cfg.get("jobs", []))

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
