from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

try:
    from .api.router import get_router
    from .config_loader import load_config
    from .services.arbitrator import ExpressionArbiter, ModalityClients
    from .services.adapters import NeopixelAdapter, OledAdapter, SpeakAdapter, HeadAdapter, PiServoAdapter
    from .services.state import SemanticExpressionEngine
except Exception:  # pragma: no cover
    from api.router import get_router  # type: ignore
    from config_loader import load_config  # type: ignore
    from services.arbitrator import ExpressionArbiter, ModalityClients  # type: ignore
    from services.adapters import NeopixelAdapter, OledAdapter, SpeakAdapter, HeadAdapter, PiServoAdapter  # type: ignore
    from services.state import SemanticExpressionEngine  # type: ignore

logger = logging.getLogger("xExpressionService")


class xExpressionService:
    """Service wrapper for the Expression module.

    Supports both legacy usage (SemanticExpressionEngine) and the new
    async ExpressionArbiter with semantic emotion rendering.
    """

    def __init__(self, config_overrides: dict | None = None) -> None:
        self.cfg = load_config(overrides=config_overrides)
        self.engine = SemanticExpressionEngine(self.cfg)
        self.arbiter = self._build_arbiter()

    def _build_arbiter(self) -> ExpressionArbiter:
        adp_cfg = self.cfg.get("adapters", {}) if isinstance(self.cfg.get("adapters"), dict) else {}
        enabled = bool(adp_cfg.get("enabled", True))
        if not enabled:
            logger.info("Adapters disabled in config; arbiter without clients")
            return ExpressionArbiter(ModalityClients(), config=self.cfg.get("arbiter", {}))
        
        gateway_url = str(adp_cfg.get("gateway_url", "http://127.0.0.1:8080")).rstrip("/")
        
        clients = ModalityClients(
            neopixel=NeopixelAdapter(gateway_url, adp_cfg.get("neopixel_timeout", 2.0)),
            oled=OledAdapter(gateway_url, adp_cfg.get("oled_timeout", 2.0)),
            speak=SpeakAdapter(gateway_url, adp_cfg.get("speak_timeout", 4.0)),
            head=HeadAdapter(gateway_url, adp_cfg.get("head_timeout", 1.0)),
            piservo=PiServoAdapter(gateway_url, adp_cfg.get("head_timeout", 1.0)),
        )
        return ExpressionArbiter(clients, config=self.cfg.get("arbiter", {}))

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def get_state(self) -> dict:
        return self.engine.get_state()

    def status(self) -> dict:
        return self.engine.status()

    def apply(self, payload: dict, *, source: str = "service", reason: str = "manual") -> dict:
        return self.engine.apply(payload, source=source, reason=reason)

    def event(self, event_type: str, data: dict | None = None) -> dict:
        return self.engine.event(event_type, data)

    def on_interaction_event(self, event_type: str, data: dict | None = None) -> None:
        self.engine.on_interaction_event(event_type, data)


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    service = xExpressionService()
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Get the router and inject arbiter
        router = get_router(service.engine)
        router.set_arbiter(service.arbiter)
        app.include_router(router)
        try:
            yield
        finally:
            pass
    
    app = FastAPI(lifespan=lifespan)
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    server = cfg.get("server", {}) if isinstance(cfg.get("server", {}), dict) else {}
    uvicorn.run(create_app(), host=str(server.get("host", "0.0.0.0")), port=int(server.get("port", 8111)))