from __future__ import annotations
from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api import get_router
    from .services.runner import EarRunner
    from .services.driver import ServoConfig
except Exception:
    from config_loader import load_config  # type: ignore
    from api import get_router  # type: ignore
    from services.runner import EarRunner  # type: ignore
    from services.driver import ServoConfig  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    left = ServoConfig(**cfg.get("left", {"gpio": 12}))
    right = ServoConfig(**cfg.get("right", {"gpio": 13}))
    runner = EarRunner(left_cfg=left, right_cfg=right)
    app = FastAPI()
    app.include_router(get_router(runner))
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg.get("server", {}).get("host", "0.0.0.0")), port=int(cfg.get("server", {}).get("port", 8093)))
