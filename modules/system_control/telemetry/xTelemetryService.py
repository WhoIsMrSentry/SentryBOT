from __future__ import annotations
from fastapi import FastAPI

from .config_loader import load_config
from .api.router import get_router


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    app = FastAPI(title="Telemetry Service")
    app.include_router(get_router(cfg))
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config(None)
    server = cfg.get("server", {})
    uvicorn.run(
        create_app(),
        host=str(server.get("host", "127.0.0.1")),
        port=int(server.get("port", 8097)),
    )
