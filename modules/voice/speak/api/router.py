from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict

from fastapi import APIRouter

from modules.common.latency_trace import latency_trace

if TYPE_CHECKING:
    from modules.voice.speak.xSpeakService import SpeakService

logger = logging.getLogger("speak.api")


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
            )
        except Exception as exc:
            logger.exception("/speak/say failed")
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            return {"ok": False, "trace_id": trace_id, "error": repr(exc)}

    @router.post("/speak/say_stream")
    async def say_stream(payload: dict) -> Dict[str, Any]:
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
        latency_trace.ensure(trace_id, {"component": "speak.stream", "chunks": len(chunks)})
        stream_jobs[job_id] = {
            "status": "running",
            "created_at": time.time(),
            "done_chunks": 0,
            "total_chunks": len(chunks),
            "trace_id": trace_id,
            "error": "",
        }

        async def run() -> None:
            try:
                from modules.voice.speak.services.player import _play_stop

                _play_stop.clear()
                print(f"\n========================================\n🤖 [SentryBOT ({payload.get('language') or 'auto'})]:\n{text}\n========================================\n", flush=True)
                for index, chunk in enumerate(chunks, start=1):
                    if _play_stop.is_set():
                        stream_jobs[job_id]["status"] = "interrupted"
                        latency_trace.finish(trace_id, "interrupted")
                        return
                    latency_trace.mark(trace_id, "tts.chunk_start", {"index": index})
                    result = await asyncio.to_thread(
                        service.speak,
                        chunk,
                        engine=payload.get("engine"),
                        tone=payload.get("tone"),
                        speaker_wav=payload.get("speaker_wav"),
                        language=payload.get("language"),
                        trace_id=trace_id,
                    )
                    if not result.get("ok"):
                        raise RuntimeError(str(result.get("detail") or result.get("error") or "TTS failed"))
                    stream_jobs[job_id]["done_chunks"] = index
                stream_jobs[job_id]["status"] = "done"
            except Exception as exc:
                stream_jobs[job_id]["status"] = "failed"
                stream_jobs[job_id]["error"] = repr(exc)
                latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})

        asyncio.create_task(run())
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
