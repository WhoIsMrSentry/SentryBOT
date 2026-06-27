from fastapi import APIRouter

from modules.agent_core.api.core import get_core_router
from modules.agent_core.api.state import get_state_router
from modules.agent_core.api.actions import get_actions_router
from modules.agent_core.api.profile import get_profile_router


def get_router(agent) -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["Agent Core"])

    router.include_router(get_core_router(agent))
    router.include_router(get_state_router(agent))
    router.include_router(get_actions_router(agent))
    router.include_router(get_profile_router(agent))

    return router
