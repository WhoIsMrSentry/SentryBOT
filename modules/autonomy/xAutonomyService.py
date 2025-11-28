from __future__ import annotations
from fastapi import FastAPI
from .config_loader import load_config
from .services.brain import AutonomyBrain
from .api.router import get_router

def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config()
    brain = AutonomyBrain(cfg)
    brain.start()
    
    app = FastAPI(title="Autonomy Service")
    app.include_router(get_router(brain))
    return app

class xAutonomyService:
    def __init__(self, config_overrides: dict | None = None):
        self.cfg = load_config(overrides=config_overrides)
        self.brain = AutonomyBrain(self.cfg)

    def start(self):
        self.brain.start()

    def stop(self):
        self.brain.stop()

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(), host="0.0.0.0", port=8100)
