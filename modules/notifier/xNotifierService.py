from __future__ import annotations
from fastapi import FastAPI

import logging

from .config_loader import load_config
from .api.router import get_router
from .services.telegram_bot import build_telegram_bot


logger = logging.getLogger("notifier")


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    bot = build_telegram_bot(cfg)

    app = FastAPI(title="Notifier Service")
    app.include_router(get_router(cfg, bot))

    polling_enabled = cfg.get("telegram", {}).get("polling", {}).get("enabled", False)
    if bot and polling_enabled:
        @app.on_event("startup")
        async def _start_bot() -> None:
            logger.info("starting telegram bot polling")
            await bot.start()

        @app.on_event("shutdown")
        async def _stop_bot() -> None:
            logger.info("stopping telegram bot polling")
            await bot.stop()
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config(None)
    uvicorn.run(create_app(), host=str(cfg["server"].get("host", "0.0.0.0")), port=int(cfg["server"].get("port", 8096)))
