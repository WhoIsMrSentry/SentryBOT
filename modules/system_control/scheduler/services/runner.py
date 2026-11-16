from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional

from modules.common.time_utils import parse_hhmm

logger = logging.getLogger("scheduler.runner")


class Scheduler:
    def __init__(
        self,
        jobs: List[Dict[str, Any]] | None = None,
        gateway_base_url: str = "http://127.0.0.1:8080",
        services: Dict[str, Any] | None = None,
        persist_path: str | Path | None = None,
    ) -> None:
        self.gateway_base_url = str(gateway_base_url).rstrip("/")
        self._lock = threading.Lock()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._results: Dict[str, Dict[str, Any]] = {}
        self._last_schedule_run: Dict[str, str] = {}
        self._dynamic_job_ids: set[str] = set()
        self._running = False
        # Event loop captured at start(); lets sync callers (HTTP routes)
        # schedule job tasks safely via call_soon_threadsafe (R39).
        self._loop: asyncio.AbstractEventLoop | None = None
        # In-process services handed to job handlers (speak/interactions/...).
        self._services: Dict[str, Any] = dict(services or {})
        self._http_client: Optional[Any] = None
        self._persist_path: Optional[Path] = Path(persist_path) if persist_path else None
        # Per-job in-flight guard: max_instances=1 semantics so a manual
        # run_once never overlaps the periodic loop execution (R59).
        self._inflight: Dict[str, bool] = {}

        for job in jobs or []:
            self.add_or_update_job(job, persist=False)
        if self._persist_path is not None:
            self._load_persisted_jobs()

    def _normalize_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        jid = str(job.get("id", "")).strip() or f"job_{int(time.time() * 1000)}"
        kind = str(job.get("kind", "http")).strip().lower()
        raw_at = job.get("at", job.get("schedule_time"))
        at_str: Optional[str] = None
        if raw_at is not None and str(raw_at).strip():
            parsed = parse_hhmm(str(raw_at).strip())
            if parsed is None:
                raise ValueError(f"invalid schedule time (expected HH:MM): {raw_at!r}")
            at_str = f"{parsed[0]:02d}:{parsed[1]:02d}"

        return {
            "id": jid,
            "enabled": bool(job.get("enabled", True)),
            "kind": kind,
            "every_s": max(0.5, float(job.get("every_s", 60.0))),
            "at": at_str,
            "method": str(job.get("method", "GET")).upper(),
            "url": str(job.get("url", "")).strip(),
            "path": str(job.get("path", "")).strip(),
            "params": job.get("params") if isinstance(job.get("params"), dict) else None,
            "json": job.get("json") if isinstance(job.get("json"), dict) else None,
            "timeout_s": max(0.1, float(job.get("timeout_s", 1.0))),
            "max_retries": max(0, int(job.get("max_retries", 0))),
            "retry_delay_s": max(0.05, float(job.get("retry_delay_s", 5.0))),
            "text": str(job.get("text", "")),
            "event": str(job.get("event", "")),
            "target": str(job.get("target", "")),
            "channel": str(job.get("channel", "telegram")).strip() or "telegram",
            "initial_delay_s": max(0.0, float(job.get("initial_delay_s", 0.0))),
        }

    def _load_persisted_jobs(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        norm = self.add_or_update_job(item, persist=False)
                        with self._lock:
                            self._dynamic_job_ids.add(norm["id"])
        except Exception as exc:
            logger.warning("Failed to load persisted scheduler jobs from %s: %s", self._persist_path, exc)

    def _save_persisted_jobs(self) -> None:
        if self._persist_path is None:
            return
        with self._lock:
            dynamic = [
                dict(self.jobs[jid])
                for jid in sorted(self._dynamic_job_ids)
                if jid in self.jobs
            ]
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_name(
                f".{self._persist_path.name}.{threading.get_ident()}.tmp"
            )
            tmp_path.write_text(json.dumps(dynamic, ensure_ascii=True, indent=2), encoding="utf-8")
            os.replace(tmp_path, self._persist_path)
        except Exception as exc:
            logger.warning("Failed to persist scheduler jobs to %s: %s", self._persist_path, exc)

    def _ensure_task_locked(self, job_id: str) -> None:
        if not self._running:
            return
        job = self.jobs.get(job_id)
        if not job or not bool(job.get("enabled", True)):
            return

        def _spawn_on_loop() -> None:
            """Runs on the event loop thread; swaps tasks atomically."""
            with self._lock:
                cur = self.jobs.get(job_id)
                if not cur or not bool(cur.get("enabled", True)) or not self._running:
                    return
                old = self._tasks.get(job_id)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return
                # Create the replacement FIRST so the job is never left
                # without a loop even if the old task cancel races.
                self._tasks[job_id] = loop.create_task(self._job_loop(job_id))
                if old is not None and old is not self._tasks[job_id] and not old.done():
                    old.cancel()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self._loop  # sync caller: defer to captured loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(_spawn_on_loop)
        except RuntimeError:
            # Event loop already closed; scheduler is shutting down.
            pass

    def start(self) -> None:
        with self._lock:
            self._running = True
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            for job_id in list(self.jobs.keys()):
                self._ensure_task_locked(job_id)

    async def stop(self) -> None:
        with self._lock:
            self._running = False
            tasks = list(self._tasks.values())
            self._tasks.clear()
            client = self._http_client
            self._http_client = None
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if client is not None and hasattr(client, "aclose"):
            try:
                await client.aclose()
            except Exception as exc:
                logger.debug("Scheduler HTTP client close failed: %s", exc)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(job) for _, job in sorted(self.jobs.items(), key=lambda kv: kv[0])]

    def list_results(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._results.items()}

    def add_or_update_job(self, job: Dict[str, Any], *, persist: bool = False) -> Dict[str, Any]:
        normalized = self._normalize_job(job)
        jid = normalized["id"]
        with self._lock:
            self.jobs[jid] = normalized
            if persist:
                self._dynamic_job_ids.add(jid)
            self._ensure_task_locked(jid)
        if persist:
            self._save_persisted_jobs()
        return normalized

    def remove_job(self, job_id: str) -> bool:
        jid = str(job_id).strip()
        if not jid:
            return False
        with self._lock:
            existed = jid in self.jobs
            self.jobs.pop(jid, None)
            self._results.pop(jid, None)
            self._last_schedule_run.pop(jid, None)
            was_dynamic = jid in self._dynamic_job_ids
            self._dynamic_job_ids.discard(jid)
            t = self._tasks.pop(jid, None)
        if t is not None:
            t.cancel()
        if existed and was_dynamic:
            self._save_persisted_jobs()
        return existed

    async def run_once(self, job_id: str) -> Dict[str, Any]:
        jid = str(job_id).strip()
        with self._lock:
            job = dict(self.jobs.get(jid, {})) if jid in self.jobs else None
            if job is not None and self._inflight.get(jid):
                return {"ok": False, "error": "job_in_flight", "id": jid}
            if job is not None:
                self._inflight[jid] = True
        if not job:
            return {"ok": False, "error": "job_not_found", "id": jid}
        try:
            return await self._execute_job(job)
        finally:
            with self._lock:
                self._inflight[jid] = False

    @staticmethod
    def _seconds_until_next_hhmm(hh: int, mm: int, now: Optional[datetime] = None) -> float:
        cur = now or datetime.now()
        target = cur.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target < cur:
            target = target + timedelta(days=1)
        return max(0.0, (target - cur).total_seconds())

    async def _job_loop(self, job_id: str) -> None:
        with self._lock:
            first = dict(self.jobs.get(job_id, {})) if job_id in self.jobs else {}
        delay = float(first.get("initial_delay_s", 0.0) or 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        while True:
            with self._lock:
                if not self._running:
                    break
                job = dict(self.jobs.get(job_id, {})) if job_id in self.jobs else None
            if not job:
                break
            if not bool(job.get("enabled", True)):
                await asyncio.sleep(max(0.5, float(job.get("every_s", 60.0))))
                continue

            at_spec = job.get("at")
            if isinstance(at_spec, str) and at_spec:
                parsed = parse_hhmm(at_spec)
                if parsed is not None:
                    now = datetime.now()
                    run_key = now.strftime("%Y-%m-%d %H:%M")
                    if (now.hour, now.minute) != parsed or self._last_schedule_run.get(job_id) == run_key:
                        wait_s = min(30.0, max(0.5, self._seconds_until_next_hhmm(parsed[0], parsed[1], now)))
                        await asyncio.sleep(wait_s)
                        continue
                    self._last_schedule_run[job_id] = run_key

            # Deadline-based pacing: the interval targets fixed wall-clock
            # spacing regardless of execution duration (no drift, R60).
            started_at = time.monotonic()
            skipped = False
            with self._lock:
                if self._inflight.get(job_id):
                    skipped = True
                else:
                    self._inflight[job_id] = True
            try:
                if not skipped:
                    await self._execute_job(job)
            finally:
                with self._lock:
                    self._inflight[job_id] = False

            if isinstance(at_spec, str) and at_spec:
                await asyncio.sleep(1.0)
                continue
            every_s = max(0.5, float(job.get("every_s", 60.0)))
            elapsed = time.monotonic() - started_at
            await asyncio.sleep(max(0.0, every_s - elapsed))

    def _build_gateway_url(self, path: str) -> str:
        path = str(path).strip()
        if not path:
            return self.gateway_base_url
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.gateway_base_url}/{path.lstrip('/')}"

    async def _request_http(
        self,
        method: str,
        url: str,
        timeout_s: float,
        params: Dict[str, Any] | None,
        payload: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        try:
            import httpx  # type: ignore
        except Exception:
            return {"ok": False, "error": "httpx_not_installed"}

        t0 = time.perf_counter()
        try:
            with self._lock:
                client = self._http_client
                if client is None:
                    client = httpx.AsyncClient()
                    self._http_client = client
            resp = await client.request(method, url, params=params, json=payload, timeout=timeout_s)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            body: Any
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return {
                "ok": bool(200 <= resp.status_code < 300),
                "status_code": int(resp.status_code),
                "latency_ms": latency_ms,
                "body": body,
            }
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}

    async def _execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        from modules.common.job_types import JobContext, JobDefinition, get_job_registry  # type: ignore

        jid = str(job.get("id", ""))
        kind = str(job.get("kind", "http")).lower()
        max_retries = max(0, int(job.get("max_retries", 0)))
        retry_delay_s = max(0.05, float(job.get("retry_delay_s", 5.0)))

        registry = get_job_registry()
        handler = registry.get(kind)

        if handler is None:
            return {
                "id": jid,
                "kind": kind,
                "ok": False,
                "error": f"unknown_job_kind:{kind}",
                "at": time.time(),
            }

        job_def = JobDefinition(
            id=jid,
            kind=kind,
            enabled=bool(job.get("enabled", True)),
            timeout_s=float(job.get("timeout_s", 1.0)),
            max_retries=max_retries,
            retry_delay_s=retry_delay_s,
            params={
                "method": job.get("method", "GET"),
                "url": job.get("url"),
                "path": job.get("path"),
                "params": job.get("params"),
                "json": job.get("json"),
                "text": job.get("text", ""),
                "event": job.get("event", ""),
                "type": job.get("event", ""),
                "target": job.get("target", ""),
                "key": job.get("key", "operational"),
                "value": job.get("value", job.get("target", "idle")),
                "channel": job.get("channel", "telegram"),
            },
            metadata={
                "gateway_base_url": self.gateway_base_url,
                "job_config": job,
            },
        )

        services: Dict[str, Any] = {
            "gateway_base_url": self.gateway_base_url,
            **self._services,
        }

        attempt = 0
        last: Dict[str, Any] = {"ok": False, "error": "not_executed"}

        while attempt <= max_retries:
            attempt += 1
            try:
                if hasattr(handler, "execute"):
                    context = JobContext(job_def, dict(services))
                    result = await handler.execute(context)
                    ok = True
                    if isinstance(result, dict) and "status" in result and isinstance(result["status"], int):
                        ok = 200 <= result["status"] < 300
                    last = {"ok": ok, "result": result}
                else:
                    last = await self._execute_legacy(job)

                if last.get("ok"):
                    break
            except RuntimeError as exc:
                if "not available" in str(exc).lower():
                    last = await self._execute_legacy(job)
                    if last.get("ok"):
                        break
                else:
                    last = {"ok": False, "error": str(exc)}
            except Exception as exc:
                last = {"ok": False, "error": str(exc)}

            if attempt <= max_retries:
                await asyncio.sleep(retry_delay_s)
                continue

        result = {
            "id": jid,
            "kind": kind,
            "ok": bool(last.get("ok", False)),
            "attempts": attempt,
            "at": time.time(),
            **last,
        }

        with self._lock:
            self._results[jid] = result
        return result

    async def _execute_legacy(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy job execution for backward compatibility."""
        kind = str(job.get("kind", "http")).lower()
        timeout_s = max(0.1, float(job.get("timeout_s", 1.0)))

        def _gateway(path: str) -> str:
            return self._build_gateway_url(path)

        if kind == "http":
            method = str(job.get("method", "GET")).upper()
            url = str(job.get("url", "")).strip() or self._build_gateway_url(str(job.get("path", "")))
            return await self._request_http(method, url, timeout_s, job.get("params"), job.get("json"))
        elif kind == "speak":
            payload = {"text": str(job.get("text", "Zamanlanmis mesaj"))}
            return await self._request_http("POST", _gateway("/speak/say"), timeout_s, None, payload)
        elif kind == "interaction_event":
            payload = {"type": str(job.get("event", "scheduler.tick"))}
            return await self._request_http("POST", _gateway("/interactions/event"), timeout_s, None, payload)
        elif kind == "diagnostics":
            return await self._request_http("POST", _gateway("/diagnostics/run"), timeout_s, None, None)
        elif kind == "state_set":
            payload = (
                job.get("json")
                if isinstance(job.get("json"), dict)
                else {"operational": str(job.get("target", "idle"))}
            )
            return await self._request_http("POST", _gateway("/state/set"), timeout_s, None, payload)
        elif kind == "notify":
            channel = str(job.get("channel", "telegram")).strip().lower()
            endpoint = "/notify/discord" if channel == "discord" else "/notify/telegram"
            payload = {"text": str(job.get("text", "scheduler notify"))}
            return await self._request_http("POST", _gateway(endpoint), timeout_s, None, payload)
        else:
            return {"ok": False, "error": f"unknown_job_kind:{kind}"}