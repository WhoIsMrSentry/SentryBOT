"""Process-local Gateway TCP readiness and shutdown coordination."""
from __future__ import annotations

import socket
import threading
import time
from typing import Callable, Optional

_LOCK = threading.RLock()
_STATE: str = "idle"  # idle | booting | ready | stopping
_HOST: str = "127.0.0.1"
_PORT: int = 8080


def mark_gateway_booting(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Record that gateway lifespan startup has begun before the HTTP socket is bound."""
    global _STATE, _HOST, _PORT
    with _LOCK:
        _STATE = "booting"
        clean_host = str(host or "127.0.0.1").strip()
        _HOST = "127.0.0.1" if clean_host in {"", "0.0.0.0", "::", "[::]"} else clean_host
        try:
            _PORT = max(1, int(port))
        except (TypeError, ValueError):
            _PORT = 8080


def mark_gateway_ready() -> None:
    """Record that the gateway HTTP socket is accepting connections."""
    global _STATE
    with _LOCK:
        if _STATE != "stopping":
            _STATE = "ready"


def mark_gateway_stopping() -> None:
    """Record that gateway shutdown has started so background pollers/clients exit cleanly."""
    global _STATE
    with _LOCK:
        _STATE = "stopping"


def mark_gateway_idle() -> None:
    """Reset readiness state after full shutdown (safe for repeated tests in one process)."""
    global _STATE
    with _LOCK:
        _STATE = "idle"


def is_gateway_stopping() -> bool:
    with _LOCK:
        return _STATE == "stopping"


def is_gateway_booting() -> bool:
    with _LOCK:
        return _STATE == "booting"


def probe_gateway_tcp(timeout_s: float = 0.05) -> bool:
    with _LOCK:
        host, port = _HOST, _PORT
    try:
        with socket.create_connection((host, port), timeout=max(0.01, float(timeout_s))):
            return True
    except OSError:
        return False


def wait_if_booting(
    *,
    stop_check: Optional[Callable[[], bool]] = None,
    timeout_s: float = 6.0,
) -> bool:
    """Pause background polling while the gateway is booting until its TCP port accepts or stops."""
    if not is_gateway_booting():
        return not is_gateway_stopping()
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    while is_gateway_booting() and time.monotonic() < deadline:
        if callable(stop_check) and stop_check():
            return False
        if probe_gateway_tcp(timeout_s=0.05):
            mark_gateway_ready()
            return True
        time.sleep(0.08)
    if is_gateway_booting():
        mark_gateway_ready()
    return not is_gateway_stopping()


__all__ = [
    "is_gateway_booting",
    "is_gateway_stopping",
    "mark_gateway_booting",
    "mark_gateway_idle",
    "mark_gateway_ready",
    "mark_gateway_stopping",
    "probe_gateway_tcp",
    "wait_if_booting",
]
