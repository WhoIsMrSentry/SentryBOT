from __future__ import annotations
from fastapi import APIRouter
from typing import TYPE_CHECKING
import asyncio
import logging
import re
import time
import uuid

if TYPE_CHECKING:
    from modules.speak.xSpeakService import SpeakService


logger = logging.getLogger("speak.api")

def get_router(service: SpeakService) -> APIRouter:
    router = APIRouter()
    stream_jobs: dict[str, dict] = {}

    def _split_text_chunks(text: str, max_chars: int = 180) -> list[str]:
        raw = str(text or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
        chunks: list[str] = []
        for part in parts:
            if len(part) <= max_chars:
                chunks.append(part)
                continue
            # Long sentence fallback: hard wrap by words.
            words = part.split()
            buf = []
            for w in words:
                candidate = (" ".join(buf + [w])).strip()
                if len(candidate) > max_chars and buf:
                    chunks.append(" ".join(buf))
                    buf = [w]
                else:
                    buf.append(w)
            if buf:
                chunks.append(" ".join(buf))
        return chunks

    @router.get("/speak/status")
    async def status():
        return {"ready": getattr(service, "tts", None) is not None}

    @router.post("/speak/stop")
    async def stop():
        """Stop in-progress TTS playback immediately."""
        try:
            return await asyncio.to_thread(service.stop_speaking)
        except Exception as e:
            logger.exception("/speak/stop failed")
            return {"ok": False, "error": repr(e)}

    @router.post("/speak/say")
    async def say(payload: dict):
        text = str(payload.get("text", "")).strip()
        engine = payload.get("engine")
        tone = payload.get("tone")
        speaker_wav = payload.get("speaker_wav")
        language = payload.get("language")
        if not text:
            return {"ok": False, "error": "text is empty"}
        
        logger.info("TTS >>> %s (engine=%s)", text, engine or "default")
        try:
            # Offload blocking TTS to thread to avoid event loop freeze
            return await asyncio.to_thread(
                service.speak,
                text,
                engine=engine,
                tone=tone,
                speaker_wav=speaker_wav,
                language=language,
            )
        except Exception as e:
            logger.exception("/speak/say failed")
            return {"ok": False, "error": repr(e)}

    @router.post("/speak/say_stream")
    async def say_stream(payload: dict):
        """Start clause-chunked TTS in background for lower perceived latency."""
        text = str(payload.get("text", "")).strip()
        engine = payload.get("engine")
        tone = payload.get("tone")
        speaker_wav = payload.get("speaker_wav")
        language = payload.get("language")
        max_chars = int(payload.get("max_chunk_chars", 180) or 180)
        if not text:
            return {"ok": False, "error": "text is empty"}

        chunks = _split_text_chunks(text, max_chars=max_chars)
        if not chunks:
            return {"ok": False, "error": "text has no speakable chunks"}

        job_id = uuid.uuid4().hex[:12]
        stream_jobs[job_id] = {
            "status": "running",
            "created_at": time.time(),
            "done_chunks": 0,
            "total_chunks": len(chunks),
            "error": "",
        }

        async def _run():
            try:
                from modules.speak.services.player import _play_stop

                for idx, chunk in enumerate(chunks, start=1):
                    if _play_stop.is_set():
                        job = stream_jobs.get(job_id)
                        if job is not None:
                            job["status"] = "interrupted"
                        return
                    await asyncio.to_thread(
                        service.speak,
                        chunk,
                        engine=engine,
                        tone=tone,
                        speaker_wav=speaker_wav,
                        language=language,
                    )
                    job = stream_jobs.get(job_id)
                    if job is not None:
                        job["done_chunks"] = idx
            except Exception as exc:
                job = stream_jobs.get(job_id)
                if job is not None:
                    job["status"] = "failed"
                    job["error"] = repr(exc)
                return

            job = stream_jobs.get(job_id)
            if job is not None:
                job["status"] = "done"

        asyncio.create_task(_run())
        return {"ok": True, "job_id": job_id, "chunks": len(chunks)}

    @router.get("/speak/jobs/{job_id}")
    async def job_status(job_id: str):
        job = stream_jobs.get(str(job_id))
        if not job:
            return {"ok": False, "error": "job not found"}
        return {"ok": True, "job": job}

    @router.post("/speak/play")
    async def play(payload: dict):
        import base64
        data_b64 = payload.get("data")
        if not data_b64:
            return {"ok": False, "error": "data (base64 WAV) is required"}
        try:
            buf = base64.b64decode(data_b64)
            return service.play_wav(buf)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return router
