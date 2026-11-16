from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore
    HTTPException = ValueError  # type: ignore
    BaseModel = object  # type: ignore

from ..xLogService import get_memory_handler

_LEVEL_MAP: Dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


if APIRouter is not None:
    router = APIRouter(prefix="/logs", tags=["logs"])  # type: ignore

    class LevelChange(BaseModel):  # type: ignore
        logger: str
        level: str

    @router.get("/")
    def list_logs(n: int = 200) -> Dict[str, Any]:
        bounded = max(1, min(int(n), 5000))
        handler = get_memory_handler()
        items = handler.tail(bounded) if handler else []
        return {"count": len(items), "items": items}

    @router.post("/level")
    def set_level(payload: LevelChange) -> Dict[str, str]:
        normalized = str(payload.level or "").strip().upper()
        if normalized not in _LEVEL_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid log level {payload.level!r}; allowed={sorted(_LEVEL_MAP)}",
            )
        log = logging.getLogger(payload.logger)
        log.setLevel(_LEVEL_MAP[normalized])
        return {"status": "ok", "logger": payload.logger, "level": normalized}
else:  # Placeholder to avoid import error when FastAPI not installed
    router = None  # type: ignore
