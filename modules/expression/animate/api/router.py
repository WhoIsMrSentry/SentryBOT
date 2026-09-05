from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Optional

try:
    from ..xAnimateService import xAnimateService
except Exception:
    from modules.expression.animate.xAnimateService import xAnimateService  # type: ignore


def get_router(anim: xAnimateService) -> APIRouter:
    r = APIRouter(prefix="/animate")

    @r.get("/list")
    def list_animations():
        return {"ok": True, "animations": anim.list()}

    @r.post("/run")
    def run(name: str, speed: float = 1.0, loop: bool = Query(False)):
        import threading

        result = {"ok": False}

        def _worker():
            result["ok"] = bool(anim.run(name, speed=speed, loop=loop))

        t = threading.Thread(target=_worker, daemon=True, name=f"animate-{name}")
        t.start()
        t.join(timeout=max(1.0, float(anim.cfg.get("run_timeout_s", 30.0))))
        if t.is_alive():
            anim.stop_run()
            return {"ok": False, "error": "animation timeout"}
        return {"ok": bool(result["ok"])}

    @r.post("/stop")
    def stop():
        anim.stop_run()
        return {"ok": True}

    return r
