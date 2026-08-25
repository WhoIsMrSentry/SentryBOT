from __future__ import annotations
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api import get_router
    from .services.runner import NeoRunner
    from .services.driver import NeoDriverConfig
except Exception:  # when run as script
    from modules.visual_output.neopixel.config_loader import load_config  # type: ignore
    from modules.visual_output.neopixel.api import get_router  # type: ignore
    from modules.visual_output.neopixel.services.runner import NeoRunner  # type: ignore
    from modules.visual_output.neopixel.services.driver import NeoDriverConfig  # type: ignore

try:
    from modules.runtime_console.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    default_cfg = Path(__file__).parent / "config" / "config.yml"
    resolved_cfg_path = Path(config_path) if config_path else Path(os.getenv("NEO_CONFIG", default_cfg))
    if not resolved_cfg_path.exists():
        resolved_cfg_path = default_cfg
    cfg = load_config(config_path)

    hw = cfg.get("hardware", {})
    drv_cfg = NeoDriverConfig(
        device=str(hw.get("device", "/dev/spidev0.0")),
        num_leds=int(hw.get("num_leds", 30)),
        speed_khz=int(hw.get("speed_khz", 800)),
        ws2812_spi_khz=int(hw.get("ws2812_spi_khz", 2400)),
        backend=str(hw.get("backend", "auto")),
        order=str(hw.get("order", "GRB")),
    )

    preset_meta = cfg.get("presets_meta", {}) if isinstance(cfg.get("presets_meta", {}), dict) else {}
    runner = NeoRunner(
        drv_cfg,
        segments=hw.get("segments", []),
        presets=cfg.get("presets", {}),
        preset_store_path=str(resolved_cfg_path),
        preset_version=int(preset_meta.get("version", 1)),
        companion_cfg=cfg.get("companion", {}),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        try:
            runner.companion_set_mode("off")
            runner.clear()
        except Exception:
            pass

    app = FastAPI(lifespan=lifespan)
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
