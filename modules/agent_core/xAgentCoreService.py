from __future__ import annotations
from fastapi import FastAPI

from .config_loader import load_config
from .services.agent import AgentOrchestrator

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


class xAgentCoreService:
    """
    Servis başlatıcı — Agent Core modülünü hem kütüphane
    hem de bağımsız servis olarak çalıştırır.
    """

    def __init__(self, config_overrides: dict | None = None, autonomy_client=None):
        self.cfg = load_config()
        if config_overrides:
            self.cfg.update(config_overrides)
        self.agent = AgentOrchestrator(self.cfg, autonomy_client=autonomy_client)

    def start(self):
        self.agent.start()

    def stop(self):
        self.agent.stop()


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    app = FastAPI(title="Agent Core Service")

    agent = AgentOrchestrator(cfg)
    agent.start()

    from .api.router import get_router
    app.include_router(get_router(agent))

    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg.get("server", {}).get("host", "0.0.0.0")),
        port=int(cfg.get("server", {}).get("port", 8120)),
    )
