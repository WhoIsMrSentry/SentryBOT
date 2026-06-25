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
    svc = OTAService(cfg)
    # Optional: scan once on startup
    try:
        if bool(cfg.get("ota", {}).get("scan_on_start", False)):
            try:
                svc.scan_once("arduino")
                svc.scan_once("esp")
            except Exception:
                pass
    except Exception:
        pass

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/scan_once")
    def scan_once(target: str = Query("arduino", pattern="^(arduino|esp)$")):
        return svc.scan_once(target)

    @r.post("/upload")
    def upload(
        path: str,
        signature: str | None = Query(None),
        target: str = Query("arduino", pattern="^(arduino|esp)$"),
    ):
        """Upload firmware with optional HMAC signature verification.
        
        Query params:
            path: Path to .hex/.bin file
            signature: Optional HMAC-SHA256 signature (if security.enable_signature is True)
            target: "arduino" or "esp"
        """
        return svc.upload_path(path, signature=signature, target=target)

    @r.get("/versions")
    def versions():
        return svc.versions()

    @r.post("/versions/clear")
    def clear(target: str = Query("all", pattern="^(all|arduino|esp)$")):
        return svc.clear_versions(target)

    return r
