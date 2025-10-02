from __future__ import annotations
from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api import get_router
    from .services.runner import NeoRunner
    from .services.driver import NeoDriverConfig
except Exception:  # when run as script
    from config_loader import load_config  # type: ignore
    from api import get_router  # type: ignore
    from services.runner import NeoRunner  # type: ignore
    from services.driver import NeoDriverConfig  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)

    drv_cfg = NeoDriverConfig(
        device=str(cfg.get("hardware", {}).get("device", "/dev/spidev0.0")),
        num_leds=int(cfg.get("hardware", {}).get("num_leds", 30)),
        speed_khz=int(cfg.get("hardware", {}).get("speed_khz", 800)),
        order=str(cfg.get("hardware", {}).get("order", "GRB")),
    )

    runner = NeoRunner(drv_cfg)

    app = FastAPI()
    app.include_router(get_router(runner))
    return app


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg.get("server", {}).get("host", "0.0.0.0")),
        port=int(cfg.get("server", {}).get("port", 8092)),
    )
