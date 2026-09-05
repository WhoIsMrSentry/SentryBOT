from __future__ import annotations

import logging
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore
    BaseModel = object  # type: ignore

from ..xLogService import get_memory_handler


if APIRouter is not None:
    router = APIRouter(prefix="/logs", tags=["logs"])  # type: ignore

    class LevelChange(BaseModel):  # type: ignore
        logger: str
        level: str

    @router.get("/")
    def list_logs(n: int = 200) -> Dict[str, Any]:
        handler = get_memory_handler()
        items = handler.tail(n) if handler else []
        return {"count": len(items), "items": items}

    @router.post("/level")
    def set_level(payload: LevelChange) -> Dict[str, str]:
        log = logging.getLogger(payload.logger)
        try:
            level_value = getattr(logging, payload.level.upper())
        except Exception:
            level_value = payload.level
        log.setLevel(level_value)
        return {"status": "ok"}
else:  # Placeholder to avoid import error when FastAPI not installed
    router = None  # type: ignore
