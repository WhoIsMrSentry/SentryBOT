from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter

from ..services.runner import Scheduler


def get_router(cfg: Dict[str, Any], scheduler: Scheduler) -> APIRouter:
    r = APIRouter(prefix="/scheduler", tags=["scheduler"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/jobs")
    def jobs():
        return scheduler.list_jobs()

    @r.post("/jobs")
    def add_or_update_job(body: Dict[str, Any]):
        if not isinstance(body, dict):
            return {"ok": False, "error": "body must be an object"}
        item = scheduler.add_or_update_job(body)
        return {"ok": True, "job": item}

    @r.delete("/jobs/{job_id}")
    def remove_job(job_id: str):
        removed = scheduler.remove_job(job_id)
        return {"ok": removed}

    @r.get("/results")
    def results():
        return scheduler.list_results()

    @r.post("/run_once/{job_id}")
    async def run_once(job_id: str):
        return await scheduler.run_once(job_id)

    return r
