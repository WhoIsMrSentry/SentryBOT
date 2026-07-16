from __future__ import annotations

from fastapi import FastAPI

try:
    from .api.router import get_router
    from .config_loader import load_config
    from .services.state import SemanticExpressionEngine
except Exception:  # pragma: no cover
    from api.router import get_router  # type: ignore
    from config_loader import load_config  # type: ignore
    from services.state import SemanticExpressionEngine  # type: ignore


class xExpressionService:
    def __init__(self, config_overrides: dict | None = None) -> None:
        self.cfg = load_config(overrides=config_overrides)
        self.engine = SemanticExpressionEngine(self.cfg)

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
    engine = SemanticExpressionEngine(cfg)
    app = FastAPI()
    app.include_router(get_router(engine))
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    server = cfg.get("server", {}) if isinstance(cfg.get("server", {}), dict) else {}
    uvicorn.run(create_app(), host=str(server.get("host", "0.0.0.0")), port=int(server.get("port", 8111)))
