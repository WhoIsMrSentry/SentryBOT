from __future__ import annotations
from fastapi import APIRouter
from typing import Any, Optional

from modules.vlm_bridge.api.control import get_control_router
from modules.vlm_bridge.api.analysis import get_analysis_router
from modules.vlm_bridge.api.person import get_person_router
from modules.vlm_bridge.api.config_routes import get_config_router


def get_router(
    processor: Any,
    ardu: Optional[Any] = None,
    gateway_base_url: str = "",
) -> APIRouter:
    base_url = str(gateway_base_url).rstrip("/") if gateway_base_url else "http://127.0.0.1:8080"

    r = APIRouter(
        prefix="/vlm",
        tags=["vlm"],
        responses={404: {"description": "Not found"}},
    )

    r.include_router(get_control_router(processor, ardu, base_url))
    r.include_router(get_analysis_router(processor, base_url))
    r.include_router(get_person_router(processor, base_url))
    r.include_router(get_config_router(processor, base_url))

    return r
