"""Central logging infrastructure for SentryBOT.

Provides a unified, dependency-light logging entry point so core services
do not need to depend directly on runtime_console UI modules.
"""
from __future__ import annotations

import importlib
import logging
import threading
from typing import Any, Callable, Dict, Optional

_PROVIDER_LOCK = threading.Lock()
_LOG_PROVIDER: Dict[str, Optional[Callable[..., Any]]] = {
    "init": None,
    "memory_handler": None,
    "router": None,
}


def register_log_provider(
    *,
    init_fn: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None,
    memory_handler_fn: Optional[Callable[[], Any]] = None,
    router_fn: Optional[Callable[[], Any]] = None,
) -> None:
    """Register runtime logging backend hooks without hard-coupling common to UI layers."""
    with _PROVIDER_LOCK:
        if init_fn is not None:
            _LOG_PROVIDER["init"] = init_fn
        if memory_handler_fn is not None:
            _LOG_PROVIDER["memory_handler"] = memory_handler_fn
        if router_fn is not None:
            _LOG_PROVIDER["router"] = router_fn


def _resolve_provider_hook(key: str, attr: str) -> Optional[Callable[..., Any]]:
    with _PROVIDER_LOCK:
        hook = _LOG_PROVIDER.get(key)
    if hook is not None:
        return hook
    try:
        mod = importlib.import_module("modules.runtime_console.logwrapper.xLogService")
        fn = getattr(mod, attr, None)
        return fn if callable(fn) else None
    except Exception:
        return None


def init_logging(overrides: Optional[Dict[str, Any]] = None) -> None:
    """Initialize system-wide logging configuration.

    Uses a registered log provider hook or optional logwrapper extension if installed,
    falling back cleanly to standard library logging configuration.
    """
    hook = _resolve_provider_hook("init", "init_logging")
    if hook is not None:
        try:
            hook(overrides)
            return
        except Exception:
            pass

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
    hook = _resolve_provider_hook("memory_handler", "get_memory_handler")
    if hook is None:
        return None
    try:
        return hook()
    except Exception:
        return None


def get_router() -> Any:
    """Return FastAPI router for log querying if available."""
    hook = _resolve_provider_hook("router", "get_router")
    if hook is None:
        return None
    try:
        return hook()
    except Exception:
        return None


__all__ = [
    "register_log_provider",
    "init_logging",
    "get_logger",
    "get_memory_handler",
    "get_router",
]

