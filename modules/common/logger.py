"""Central logging infrastructure for SentryBOT.

Provides a unified, dependency-light logging entry point so core services
do not need to depend directly on runtime_console UI modules.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional


def init_logging(overrides: Optional[Dict[str, Any]] = None) -> None:
    """Initialize system-wide logging configuration.
    
    Delegates to runtime_console.logwrapper if available, or configures
    a standard stream/file handler fallback.
    """
    try:
        from modules.runtime_console.logwrapper.xLogService import init_logging as _init
        _init(overrides)
    except Exception:
        level = (overrides or {}).get("console_level", "INFO") if isinstance(overrides, dict) else "INFO"
        logging.basicConfig(
            level=getattr(logging, str(level).upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance."""
    return logging.getLogger(name)


def get_memory_handler() -> Any:
    """Return in-memory log buffer handler if registered."""
    try:
        from modules.runtime_console.logwrapper.xLogService import get_memory_handler as _get
        return _get()
    except Exception:
        return None


def get_router() -> Any:
    """Return FastAPI router for log querying if available."""
    try:
        from modules.runtime_console.logwrapper.xLogService import get_router as _get_r
        return _get_r()
    except Exception:
        return None


__all__ = [
    "init_logging",
    "get_logger",
    "get_memory_handler",
    "get_router",
]

