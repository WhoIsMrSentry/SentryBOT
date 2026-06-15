from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .xOledFacesService import xOledFacesService as xOledFacesService


def __getattr__(name: str):
    if name == "xOledFacesService":
        from .xOledFacesService import xOledFacesService

        return xOledFacesService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["xOledFacesService"]
