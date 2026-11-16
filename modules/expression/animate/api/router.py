from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

try:
    from ..xAnimateService import xAnimateService
except ImportError:
    from modules.expression.animate.xAnimateService import xAnimateService  # type: ignore


def get_router(anim: xAnimateService) -> APIRouter:
    r = APIRouter(prefix="/animate")

    @r.get("/list")
    def list_animations():
        return {"ok": True, "animations": anim.list()}

    @r.get("/status")
    def status():
        return anim.status()

    @r.post("/run")
    async def run(name: str, speed: float = 1.0, loop: bool = Query(False)):
        if not math.isfinite(speed) or speed <= 0.0:
            raise HTTPException(status_code=400, detail="speed must be finite and > 0")
        try:
            # Pre-validate name & YAML file before launching execution
            anim.load(name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"animation not found: {name}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if loop:
            anim.start_async(name, speed=speed, loop=True)
            return {"ok": True, "loop": True, "status": "running", "name": name}

        timeout_s = max(1.0, float(anim.cfg.get("run_timeout_s", 30.0)))
        try:
            ok = await asyncio.wait_for(
                run_in_threadpool(anim.run, name, speed=speed, loop=False),
                timeout=timeout_s,
            )
            return {"ok": bool(ok)}
        except asyncio.TimeoutError:
            anim.stop_run()
            return {"ok": False, "error": "animation timeout"}

    @r.post("/stop")
    def stop(return_to_rest: bool = Query(False)):
        anim.stop_run(return_to_rest=return_to_rest)
        return {"ok": True, "return_to_rest": return_to_rest}

    return r
