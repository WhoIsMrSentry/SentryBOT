from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.common.time_utils import parse_hhmm
from ..services.runner import Scheduler


class SchedulerJobPayload(BaseModel):
    """Validated payload for creating or updating a scheduled job."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    kind: str = "http"
    enabled: bool = True
    every_s: float = Field(default=60.0, ge=0.5)
    at: Optional[str] = None
    method: str = "GET"
    url: str = ""
    path: str = ""
    params: Optional[Dict[str, Any]] = None
    json_body: Optional[Dict[str, Any]] = Field(default=None, alias="json")
    timeout_s: float = Field(default=1.0, ge=0.1)
    max_retries: int = Field(default=0, ge=0)
    retry_delay_s: float = Field(default=5.0, ge=0.05)
    initial_delay_s: float = Field(default=0.0, ge=0.0)
    text: str = ""
    event: str = ""
    target: str = ""
    channel: str = "telegram"

    @field_validator("at")
    @classmethod
    def _validate_at(cls, val: Optional[str]) -> Optional[str]:
        if val is None or not str(val).strip():
            return None
        parsed = parse_hhmm(str(val).strip())
        if parsed is None:
            raise ValueError(f"invalid schedule time (expected HH:MM): {val!r}")
        return f"{parsed[0]:02d}:{parsed[1]:02d}"


def get_router(cfg: Dict[str, Any], scheduler: Scheduler) -> APIRouter:
    r = APIRouter(prefix="/scheduler", tags=["scheduler"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/jobs")
    def jobs():
        return scheduler.list_jobs()

    @r.post("/jobs")
    def add_or_update_job(body: SchedulerJobPayload):
        payload = body.model_dump(by_alias=True, exclude_none=True)
        try:
            item = scheduler.add_or_update_job(payload, persist=True)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
