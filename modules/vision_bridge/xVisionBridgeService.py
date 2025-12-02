from __future__ import annotations
from fastapi import FastAPI

try:
    from .config_loader import load_config
    from .api.router import get_router
    from .services.processor import VisionProcessor
except ImportError:
    from config_loader import load_config
    from api.router import get_router
    from services.processor import VisionProcessor

# Optional central logging
try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    
    # Initialize Vision Processor
    processor = VisionProcessor(cfg)
    
    app = FastAPI()
    app.include_router(get_router(processor))
    
    # Store processor in app state for access if needed
    app.state.processor = processor
    
    @app.on_event("startup")
    async def startup_event():
        # Optionally start stream if configured to auto-start
        pass

    @app.on_event("shutdown")
    async def shutdown_event():
        processor.stop_stream_processing()

    return app

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host=str(cfg["server"]["host"]), port=int(cfg["server"]["port"]))
