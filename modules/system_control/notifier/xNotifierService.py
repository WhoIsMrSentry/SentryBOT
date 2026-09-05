from __future__ import annotations
from fastapi import FastAPI

import logging

from contextlib import asynccontextmanager

from .config_loader import load_config
from .api.router import get_router
from .services.telegram_bot import build_telegram_bot


logger = logging.getLogger("notifier")


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    telegram_bot = build_telegram_bot(cfg)
    polling_enabled = cfg.get("telegram", {}).get("polling", {}).get("enabled", False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if telegram_bot and polling_enabled:
            logger.info("starting telegram bot polling")
            await telegram_bot.start()
        try:
            yield
        finally:
            if telegram_bot and polling_enabled:
                logger.info("stopping telegram bot polling")
                await telegram_bot.stop()

    app = FastAPI(title="Notifier Service", lifespan=lifespan)
    app.include_router(get_router(cfg, telegram_bot))
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config(None)
    uvicorn.run(create_app(), host=str(cfg["server"].get("host", "0.0.0.0")), port=int(cfg["server"].get("port", 8096)))
