from __future__ import annotations
from typing import Dict, Any, List
import asyncio


class Scheduler:
    def __init__(self, jobs: List[Dict[str, Any]] | None = None) -> None:
        self.jobs = jobs or []
        self._tasks: List[asyncio.Task] = []

    async def _job_loop(self, job: Dict[str, Any]) -> None:
        every = float(job.get("every_s", 60))
        url = str(job.get("url", ""))
        method = str(job.get("method", "GET")).upper()
        try:
            import httpx  # type: ignore
        except Exception:
            httpx = None  # type: ignore
        while True:
            if httpx and url:
                try:
                    with httpx.Client() as c:
                        c.request(method, url, timeout=1.0)
                except Exception:
                    pass
            await asyncio.sleep(every)

    def start(self) -> None:
        for j in self.jobs:
            self._tasks.append(asyncio.create_task(self._job_loop(j)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
