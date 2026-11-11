from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api import get_router
    from .services.runner import EarRunner
    from .services.driver import ServoConfig
except ImportError:
    from modules.expression.piservo.config_loader import load_config  # type: ignore
    from modules.expression.piservo.api import get_router  # type: ignore
    from modules.expression.piservo.services.runner import EarRunner  # type: ignore
    from modules.expression.piservo.services.driver import ServoConfig  # type: ignore

try:
    from modules.common.logger import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except ImportError:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    left = ServoConfig(**cfg.get("left", {"gpio": 12}))
    right = ServoConfig(**cfg.get("right", {"gpio": 13}))
    motion = cfg.get("motion") or {}
    runner = EarRunner(
        left_cfg=left,
        right_cfg=right,
        smooth_enabled=bool(motion.get("smooth_enabled", True)),
        ramp_hz=float(motion.get("ramp_hz", 50.0)),
        max_speed_deg_s=float(motion.get("max_speed_deg_s", 360.0)),
        idle_detach_ms=int(motion.get("idle_detach_ms", 800)),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            runner.close()

    app = FastAPI(lifespan=lifespan)
    app.state.ear_runner = runner
    app.include_router(get_router(runner))
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    srv = cfg.get("server", {})
    uvicorn.run(
        create_app(),
        host=str(srv.get("host", "0.0.0.0")),
        port=int(srv.get("port", 8093)),
    )
