from __future__ import annotations

# Public API surface for the neopixel module
try:
    from .xNeopixelService import create_app  # noqa: F401
except Exception:  # pragma: no cover - import flexibility when run as script
    pass
