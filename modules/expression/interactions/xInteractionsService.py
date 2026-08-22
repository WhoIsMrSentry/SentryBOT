from __future__ import annotations

from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api.router import get_router
    from .services.engine import InteractionEngine
except Exception:  # pragma: no cover
    from config_loader import load_config  # type: ignore
    from api.router import get_router  # type: ignore
    from services.engine import InteractionEngine  # type: ignore


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    engine = InteractionEngine(cfg)
    engine.start()
    app = FastAPI()
    app.include_router(get_router(engine))
    return app


class xInteractionsService:
    def __init__(self, config_overrides: dict | None = None) -> None:
        self.cfg = load_config(overrides=config_overrides)
        self.engine = InteractionEngine(self.cfg)

    def start(self) -> None:
        self.engine.start()

    def stop(self) -> None:
        self.engine.stop()


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg.get("server", {}).get("host", "0.0.0.0")),
        port=int(cfg.get("server", {}).get("port", 8095)),
    )
