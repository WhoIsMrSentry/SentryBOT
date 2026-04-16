from __future__ import annotations
from fastapi import APIRouter, Query
import os

try:
    from ..config_loader import load_config
    from ..services.uploader import OTAService
except Exception:
    from modules.ota.config_loader import load_config  # type: ignore
    from modules.ota.services.uploader import OTAService  # type: ignore


def get_router(cfg: dict | None = None) -> APIRouter:
    cfg = cfg or load_config(None)
    r = APIRouter(prefix="/ota", tags=["ota"])
    svc = OTAService(cfg.get("ota", {}))
    # Optional: scan once on startup
    try:
        if bool(cfg.get("ota", {}).get("scan_on_start", False)):
            try:
                svc.scan_once()
            except Exception:
                pass
    except Exception:
        pass

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/scan_once")
    def scan_once():
        return svc.scan_once()

    @r.post("/upload")
    def upload(path: str, signature: str | None = Query(None)):
        """Upload firmware with optional HMAC signature verification.
        
        Query params:
            path: Path to .hex file
            signature: Optional HMAC-SHA256 signature (if security.enable_signature is True)
        """
        return svc.upload_path(path, signature=signature)

    @r.get("/versions")
    def versions():
        return svc.versions()

    @r.post("/versions/clear")
    def clear():
        return svc.clear_versions()

    return r
