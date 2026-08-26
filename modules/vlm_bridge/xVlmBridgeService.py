from __future__ import annotations
from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api.router import get_router
    from .services.processor import VisionProcessor
except (ImportError, ModuleNotFoundError) as rel_exc:
    # Try absolute package path as fallback (handles different import contexts)
    try:
        from modules.vlm_bridge.config_loader import load_config
        from modules.vlm_bridge.api.router import get_router
        from modules.vlm_bridge.services.processor import VisionProcessor
    except (ImportError, ModuleNotFoundError) as abs_exc:
        raise ImportError(
            f"Failed to import vlm_bridge modules. relative={rel_exc!r}; absolute={abs_exc!r}"
        ) from abs_exc

# Optional central logging
from contextlib import asynccontextmanager

try:
    from modules.runtime_console.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    
    # Initialize Vision Processor
    processor = VisionProcessor(cfg)
    
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            processor.stop_stream_processing()

    app = FastAPI(lifespan=lifespan)
    app.include_router(get_router(processor))
    
    # Store processor in app state for access if needed
    app.state.processor = processor
    return app

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]), log_config=None)
