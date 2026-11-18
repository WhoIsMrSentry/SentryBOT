"""Process-wide active persona scope shared across AI, Agent Core, Memory, and Voice."""
from __future__ import annotations

from contextlib import contextmanager
import logging
import re
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger("common.persona_scope")

DEFAULT_PERSONA_ID = "sentry"
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_LOCK = threading.RLock()
_ACTIVE_PERSONA: str = DEFAULT_PERSONA_ID
_ACTIVE_META: Dict[str, Any] = {}
_LISTENERS: List[Callable[[str, Dict[str, Any]], None]] = []
_TLS = threading.local()


def normalize_persona_id(name: Optional[str], fallback: str = DEFAULT_PERSONA_ID) -> str:
    cleaned = str(name or "").strip().lower()
    if cleaned and _SAFE_NAME_RE.match(cleaned):
        return cleaned
    fb = str(fallback or DEFAULT_PERSONA_ID).strip().lower()
    return fb if fb and _SAFE_NAME_RE.match(fb) else DEFAULT_PERSONA_ID


def get_active_persona() -> str:
    """Return thread-scoped override if active, otherwise global active persona id."""
    override = getattr(_TLS, "persona_override", None)
    if override:
        return str(override)
    with _LOCK:
        return _ACTIVE_PERSONA


def get_active_persona_meta() -> Dict[str, Any]:
    with _LOCK:
        return dict(_ACTIVE_META)


def set_active_persona(
    name: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
    notify: bool = True,
) -> str:
    """Update active persona scope and optionally notify bound subsystems."""
    global _ACTIVE_PERSONA, _ACTIVE_META
    normalized = normalize_persona_id(name)
    meta_copy = dict(meta) if isinstance(meta, dict) else {}
    with _LOCK:
        _ACTIVE_PERSONA = normalized
        _ACTIVE_META = meta_copy
        listeners = list(_LISTENERS) if notify else []
    for cb in listeners:
        try:
            cb(normalized, dict(meta_copy))
        except Exception as exc:
            logger.debug("Persona change listener failed (%s): %s", normalized, exc)
    return normalized


def register_persona_listener(cb: Callable[[str, Dict[str, Any]], None]) -> None:
    if not callable(cb):
        return
    with _LOCK:
        if cb not in _LISTENERS:
            _LISTENERS.append(cb)


def unregister_persona_listener(cb: Callable[[str, Dict[str, Any]], None]) -> None:
    with _LOCK:
        if cb in _LISTENERS:
            _LISTENERS.remove(cb)


@contextmanager
def persona_context(name: str) -> Iterator[str]:
    """Temporarily scope cognitive memory / persona operations on the current thread."""
    prev = getattr(_TLS, "persona_override", None)
    normalized = normalize_persona_id(name)
    _TLS.persona_override = normalized
    try:
        yield normalized
    finally:
        _TLS.persona_override = prev


__all__ = [
    "DEFAULT_PERSONA_ID",
    "get_active_persona",
    "get_active_persona_meta",
    "normalize_persona_id",
    "persona_context",
    "register_persona_listener",
    "set_active_persona",
    "unregister_persona_listener",
]
