from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from .api.router import get_router
from .config_loader import load_config
from .services.senders import close_senders
from .services.telegram_bot import build_telegram_bot

logger = logging.getLogger("notifier")


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    telegram_bot = build_telegram_bot(cfg)
    polling_enabled = bool(cfg.get("telegram", {}).get("polling", {}).get("enabled", False))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if telegram_bot and polling_enabled:
            logger.info("starting telegram bot polling")
            await telegram_bot.start()
        try:
            yield
        finally:
            if telegram_bot:
                logger.info("stopping telegram bot")
                await telegram_bot.stop()
            close_senders()

    app = FastAPI(title="Notifier Service", lifespan=lifespan)
    app.include_router(get_router(cfg, telegram_bot))
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config(None)
    server = cfg.get("server", {})
    uvicorn.run(
        create_app(),
        host=str(server.get("host", "127.0.0.1")),
        port=int(server.get("port", 8096)),
    )
