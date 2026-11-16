from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, FileResponse

from modules.system_control.config_center.api._helpers import is_within_repo


def get_views_router(static_dir: Path) -> APIRouter:
    r = APIRouter(tags=["config_center-ui"])

    @r.get("/ui", response_class=HTMLResponse)
    def ui():
        index_file = static_dir / "index.html"
        if not index_file.exists():
            return HTMLResponse("<h1>Config Center UI not found</h1>", status_code=404)
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    @r.get("/static/{file_path:path}")
    def serve_static(file_path: str):
        target = (static_dir / file_path).resolve()
        if not is_within_repo(target, static_dir):
            return Response(status_code=403, content="invalid path")
        if not target.exists() or not target.is_file():
            return Response(status_code=404)
        return FileResponse(str(target))

    return r
