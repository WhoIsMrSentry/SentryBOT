from __future__ import annotations

import asyncio
import base64
import logging
import re
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict

from fastapi import APIRouter

from modules.common.latency_trace import latency_trace
from modules.voice.speak.services.speech_queue import SpeechPriority, SpeechPriorityQueue

if TYPE_CHECKING:
    from modules.voice.speak.xSpeakService import SpeakService

logger = logging.getLogger("speak.api")


def _player_stop_epoch(player: Any) -> int | None:
    epoch = getattr(player, "stop_epoch", None)
    return epoch if isinstance(epoch, int) and not isinstance(epoch, bool) else None


def _clear_player_stop(player: Any) -> None:
    clear_fn = getattr(player, "clear_stop", None)
    if callable(clear_fn):
        clear_fn()
        return
    stop_evt = getattr(player, "_play_stop", None)
    if stop_evt is not None and hasattr(stop_evt, "clear"):
        stop_evt.clear()


def _split_text_chunks(text: str, max_chars: int = 180) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", raw) if part.strip()]
    chunks: list[str] = []
    for part in parts:
        words = part.split()
        buffer: list[str] = []
        for word in words:
            candidate = " ".join(buffer + [word])
            if buffer and len(candidate) > max_chars:
                chunks.append(" ".join(buffer))
                buffer = [word]
            else:
                buffer.append(word)
        if buffer:
            chunks.append(" ".join(buffer))
    return chunks


def get_router(service: SpeakService) -> APIRouter:
    router = APIRouter()
    stream_jobs: Dict[str, Dict[str, Any]] = {}
    queue_obj: SpeechPriorityQueue = getattr(service, "priority_queue", None) or SpeechPriorityQueue(
        stop_callback=service.stop
    )
    worker_lock = threading.Lock()
    worker_thread: threading.Thread | None = None

    def _prune_stream_jobs(max_items: int = 30, max_age_s: float = 180.0) -> None:
        now = time.time()
        expired = [jid for jid, info in stream_jobs.items() if now - float(info.get("created_at", 0)) > max_age_s]
        for jid in expired:
            stream_jobs.pop(jid, None)
        if len(stream_jobs) > max_items:
            sorted_keys = sorted(stream_jobs.keys(), key=lambda k: float(stream_jobs[k].get("created_at", 0)))
            for jid in sorted_keys[: len(stream_jobs) - max_items]:
                stream_jobs.pop(jid, None)

    def _run_stream_job(req_opts: Dict[str, Any]) -> None:
        job_id = str(req_opts["job_id"])
        trace_id = str(req_opts["trace_id"])
        chunks = list(req_opts["chunks"])
        payload = dict(req_opts["payload"])
        submit_epoch = req_opts.get("submit_stop_epoch")
        stop_state = req_opts.get("stop_state")
        if isinstance(stop_state, dict):
            ready = stop_state.get("ready")
            if ready is not None and hasattr(ready, "wait"):
                ready.wait(timeout=0.5)
            submit_epoch = stop_state.get("epoch", submit_epoch)
        job = stream_jobs.get(job_id)
        if job is None:
            return
        try:
            job["status"] = "running"
            player = getattr(service, "player", None)
            current_epoch = _player_stop_epoch(player)
            if submit_epoch is not None and current_epoch is not None and current_epoch != submit_epoch:
                logger.info("Stream job %s interrupted before playback", job_id)
                job["status"] = "interrupted"
                latency_trace.finish(trace_id, "interrupted", {"done_chunks": 0})
                return
            _clear_player_stop(player)
            logger.info(
                "Speaking stream (%s, %d chunks): %s",
                payload.get("language") or "auto",
                len(chunks),
                str(req_opts.get("text") or "")[:80],
            )
            for index, chunk in enumerate(chunks, start=1):
                if getattr(getattr(service, "player", None), "is_stopped", False):
                    logger.info("Stream job %s interrupted at chunk %d/%d", job_id, index, len(chunks))
                    job["status"] = "interrupted"
                    latency_trace.finish(trace_id, "interrupted", {"done_chunks": index - 1})
                    return
                latency_trace.mark(trace_id, "tts.chunk_start", {"index": index})
                result = service.speak(
                    chunk,
                    engine=payload.get("engine"),
                    tone=payload.get("tone"),
                    speaker_wav=payload.get("speaker_wav"),
                    language=payload.get("language"),
                    trace_id=f"{trace_id}-c{index}",
                    voice=payload.get("voice"),
                )
                if not result.get("ok"):
                    raise RuntimeError(str(result.get("detail") or result.get("error") or "TTS failed"))
                job["done_chunks"] = index
            job["status"] = "done"
            latency_trace.finish(trace_id, "done", {"chunks": len(chunks)})
        except Exception as exc:
            logger.warning("Stream job %s failed: %s", job_id, exc)
            job["status"] = "failed"
            job["error"] = repr(exc)
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})

    def _queue_worker() -> None:
        nonlocal worker_thread
        while True:
            req = queue_obj.get_next()
            if req is None:
                with worker_lock:
                    if queue_obj.is_empty:
                        worker_thread = None
                        return
                continue
            _run_stream_job(req.options)

    def _ensure_worker_started() -> None:
        nonlocal worker_thread
        with worker_lock:
            if worker_thread is None or not worker_thread.is_alive():
                worker_thread = threading.Thread(target=_queue_worker, daemon=True)
                worker_thread.start()

    @router.get("/speak/status")
    async def status() -> Dict[str, Any]:
        health = service.tts.health()
        return {
            "ready": bool(health.get("available", False)),
            "tts": health,
            "is_speaking": bool(getattr(service, "is_speaking", False)),
        }

    @router.get("/speak/latency/latest")
    async def latest_latency() -> Dict[str, Any]:
        trace = latency_trace.latest()
        return {"ok": trace is not None, "trace": trace}

    @router.get("/speak/latency/{trace_id}")
    async def latency(trace_id: str) -> Dict[str, Any]:
        trace = latency_trace.get(trace_id)
        return {"ok": trace is not None, "trace": trace}

    @router.post("/speak/stop")
    async def stop() -> Dict[str, Any]:
        return await asyncio.to_thread(service.stop_speaking)

    @router.post("/speak/say")
    async def say(payload: dict) -> Dict[str, Any]:
        text = str(payload.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "text is empty"}
        trace_id = str(payload.get("trace_id") or uuid.uuid4().hex[:16])
        try:
            return await asyncio.to_thread(
                service.speak,
                text,
                engine=payload.get("engine"),
                tone=payload.get("tone"),
                speaker_wav=payload.get("speaker_wav"),
                language=payload.get("language"),
                trace_id=trace_id,
                voice=payload.get("voice"),
            )
        except Exception as exc:
            logger.exception("/speak/say failed")
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            return {"ok": False, "trace_id": trace_id, "error": repr(exc)}

    @router.post("/speak/say_stream")
    async def say_stream(payload: dict) -> Dict[str, Any]:
        _prune_stream_jobs()
        text = str(payload.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "text is empty"}
        default_chunk = int(getattr(service, "stream_max_chunk_chars", 180))
        chunks = _split_text_chunks(
            text,
            max_chars=max(40, int(payload.get("max_chunk_chars", default_chunk))),
        )
        if not chunks:
            return {"ok": False, "error": "text has no speakable chunks"}

        job_id = uuid.uuid4().hex[:12]
        trace_id = str(payload.get("trace_id") or uuid.uuid4().hex[:16])
        priority = int(payload.get("priority", SpeechPriority.USER_RESPONSE))
        latency_trace.ensure(trace_id, {"component": "speak.stream", "chunks": len(chunks)})
        stream_jobs[job_id] = {
            "status": "queued",
            "created_at": time.time(),
            "done_chunks": 0,
            "total_chunks": len(chunks),
            "trace_id": trace_id,
            "error": "",
        }
        stop_state: Dict[str, Any] = {"epoch": None, "ready": threading.Event()}
        queue_obj.submit(
            text,
            priority=priority,
            options={
                "job_id": job_id,
                "trace_id": trace_id,
                "chunks": chunks,
                "payload": dict(payload),
                "text": text,
                "stop_state": stop_state,
            },
        )
        stop_state["epoch"] = _player_stop_epoch(getattr(service, "player", None))
        stop_state["ready"].set()
        _ensure_worker_started()
        return {"ok": True, "job_id": job_id, "trace_id": trace_id, "chunks": len(chunks)}

    @router.get("/speak/jobs/{job_id}")
    async def job_status(job_id: str) -> Dict[str, Any]:
        job = stream_jobs.get(str(job_id))
        return {"ok": job is not None, "job": job}

    @router.post("/speak/play")
    async def play(payload: dict) -> Dict[str, Any]:
        data_b64 = payload.get("data")
        if not data_b64:
            return {"ok": False, "error": "data (base64 WAV) is required"}
        try:
            return await asyncio.to_thread(
                service.play_wav,
                base64.b64decode(data_b64),
                trace_id=payload.get("trace_id"),
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return router
