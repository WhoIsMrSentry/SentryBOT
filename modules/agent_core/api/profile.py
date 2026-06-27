from fastapi import APIRouter, Body, Query
from typing import Optional


def get_profile_router(agent) -> APIRouter:
    router = APIRouter(tags=["agent-profile"])

    @router.get("/profile")
    def get_profile():
        rt_cfg = agent.config.get("realtime_profile", {})
        active = str(rt_cfg.get("active", "fast"))
        known = [str(k) for k, v in rt_cfg.items() if isinstance(v, dict)]
        if not known:
            known = ["fast", "normal"]
        return {
            "ok": True,
            "active": active,
            "modes": known,
            "settings": rt_cfg.get(active, {}),
        }

    @router.post("/profile/switch")
    def switch_profile(
        mode: Optional[str] = Body(default=None, embed=True),
        mode_q: Optional[str] = Query(default=None, alias="mode"),
    ):
        mode_value = mode if mode is not None else mode_q
        mode = str(mode_value or "").strip().lower()
        rt_cfg_known = agent.config.get("realtime_profile", {}) if isinstance(getattr(agent, "config", {}), dict) else {}
        valid_modes = {str(k) for k, v in rt_cfg_known.items() if isinstance(v, dict)}
        if mode not in valid_modes:
            return {"ok": False, "error": f"Invalid mode '{mode}'. Allowed: {sorted(valid_modes)}"}

        rt_cfg = agent.config.get("realtime_profile", {})
        profile = rt_cfg.get(mode, {})
        if not profile:
            return {"ok": False, "error": f"Profile '{mode}' not configured."}

        rt_cfg["active"] = mode

        applied = {}
        if hasattr(agent, "apply_realtime_profile"):
            applied = agent.apply_realtime_profile(profile) or {}
        else:
            if hasattr(agent, "persona_num_predict"):
                agent.persona_num_predict = int(profile.get("num_predict_persona", agent.persona_num_predict))
            if hasattr(agent, "num_ctx"):
                agent.num_ctx = int(profile.get("num_ctx", agent.num_ctx))
            if hasattr(agent, "temperature"):
                agent.temperature = float(profile.get("temperature", agent.temperature))
            if hasattr(agent, "request_timeout"):
                agent.request_timeout = float(profile.get("request_timeout_s", agent.request_timeout))
            applied = {
                "num_predict_persona": getattr(agent, "persona_num_predict", None),
                "num_ctx": getattr(agent, "num_ctx", None),
                "temperature": getattr(agent, "temperature", None),
                "request_timeout_s": getattr(agent, "request_timeout", None),
            }

        return {"ok": True, "active": mode, "applied": applied}

    return router
