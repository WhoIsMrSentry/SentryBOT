from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .config_loader import load_config
from .services.store import StateStore
from .api.router import get_router


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    store = StateStore(
        defaults=cfg.get("defaults", {}),
        persistence=cfg.get("persistence", {}),
        pubsub=cfg.get("pubsub", {}),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="State Manager", lifespan=lifespan)
    app.state.store = store  # type: ignore[attr-defined]
    app.include_router(get_router(store))
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config(None)
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
