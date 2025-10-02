from __future__ import annotations
from fastapi import APIRouter

try:
    from ..config_loader import load_config
    from ..services.runner import MutagenRunner
except Exception:
    from modules.mutagen.config_loader import load_config  # type: ignore
    from modules.mutagen.services.runner import MutagenRunner  # type: ignore


def get_router(cfg: dict | None = None) -> APIRouter:
    cfg = cfg or load_config(None)
    r = APIRouter(prefix="/mutagen", tags=["mutagen"])
    runner = MutagenRunner(cfg.get("mutagen", {}))

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/status")
    def status():
        return runner.status()

    @r.post("/start")
    def start():
        return runner.start()

    @r.post("/stop")
    def stop():
        return runner.stop()

    @r.post("/rescan")
    def rescan():
        return runner.rescan()

    return r
