from __future__ import annotations

import base64
import hmac
import logging
import os
import re
import shutil
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from .bootstrap import bootstrap_runtime
from .catalog import VoiceCatalog
from .config import RuntimeConfig, load_runtime_config
from .models import SynthesizeRequest
from .synth import WavLRUCache, synthesize_cached

logger = logging.getLogger("remote_tts_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

_SAFE_WAV_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.wav$", re.IGNORECASE)
_HTTP_SESSION: Optional[requests.Session] = None


def _http_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
    return _HTTP_SESSION


def _iter_wav_chunks(wav_bytes: bytes, chunk_size: int = 65536) -> Iterator[bytes]:
    for idx in range(0, len(wav_bytes), chunk_size):
        yield wav_bytes[idx : idx + chunk_size]


async def _read_bounded_body(request: Request, max_bytes: int) -> bytes:
    """Read request body incrementally while enforcing a hard streaming upper bound."""
    hard_cap = max_bytes + 65536
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > hard_cap:
                raise HTTPException(status_code=413, detail=f"Upload exceeds limit ({max_bytes} bytes)")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > hard_cap:
            raise HTTPException(status_code=413, detail=f"Upload exceeds limit ({max_bytes} bytes)")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_upload_part(content_type: str, raw_body: bytes, x_filename: Optional[str]) -> tuple[str, bytes]:
    """Extract uploaded filename + binary payload from multipart/form-data or X-Filename fallback."""
    m = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', str(content_type or ""), re.IGNORECASE)
    if not m:
        if x_filename:
            return str(x_filename), raw_body
        raise HTTPException(status_code=400, detail="Expected multipart/form-data upload")
    boundary = (m.group(1) or m.group(2)).encode("latin-1")
    for part in raw_body.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if part.startswith(b"\r\n"):
            part = part[2:]
        sep_idx = part.find(b"\r\n\r\n")
        if sep_idx >= 0:
            headers_raw = part[:sep_idx].decode("latin-1", errors="replace")
            payload = part[sep_idx + 4 :]
        else:
            sep_idx = part.find(b"\n\n")
            if sep_idx < 0:
                continue
            headers_raw = part[:sep_idx].decode("latin-1", errors="replace")
            payload = part[sep_idx + 2 :]
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        elif payload.endswith(b"\n"):
            payload = payload[:-1]
        if re.search(r'\bname=["\']?file["\']?', headers_raw, re.IGNORECASE) or "filename=" in headers_raw:
            fn_match = re.search(r'filename="([^"]*)"|filename=([^;\r\n]+)', headers_raw, re.IGNORECASE)
            raw_name = ""
            if fn_match:
                raw_name = (fn_match.group(1) if fn_match.group(1) is not None else (fn_match.group(2) or "")).strip()
            return raw_name, payload
    raise HTTPException(status_code=400, detail="Missing 'file' part in upload")


def create_app(runtime_cfg: Optional[RuntimeConfig] = None) -> FastAPI:
    cfg = runtime_cfg or load_runtime_config()
    catalog = VoiceCatalog(
        piper_root=Path(cfg.piper_root),
        xtts_root=Path(cfg.xtts_root),
    )
    wav_cache = WavLRUCache(max_entries=int(getattr(cfg, "wav_cache_max_entries", 32)))
    bootstrap_state: Dict[str, Any] = {"running": False, "last_report": None, "error": ""}

    def _run_bootstrap_bg() -> None:
        bootstrap_state["running"] = True
        try:
            report = bootstrap_runtime(cfg, force=False)
            bootstrap_state["last_report"] = report
            catalog.refresh()
            logger.info("Runtime background bootstrap finished: %s", report)
        except Exception as exc:
            bootstrap_state["error"] = str(exc)
            logger.warning("Runtime background bootstrap error: %s", exc)
        finally:
            bootstrap_state["running"] = False

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Path(cfg.tts_root).mkdir(parents=True, exist_ok=True)
        Path(cfg.piper_root).mkdir(parents=True, exist_ok=True)
        Path(cfg.xtts_root).mkdir(parents=True, exist_ok=True)
        catalog.refresh()
        if cfg.bootstrap_on_start:
            threading.Thread(target=_run_bootstrap_bg, daemon=True).start()
        yield

    app = FastAPI(title="SentryBOT Remote TTS Server", version="0.2.0", lifespan=lifespan)

    def _extract_auth_token(authorization: Optional[str], x_auth_token: Optional[str]) -> str:
        if x_auth_token:
            return str(x_auth_token).strip()
        if authorization:
            value = str(authorization).strip()
            if value.lower().startswith("bearer "):
                return value[7:].strip()
            return value
        return ""

    def _require_auth(authorization: Optional[str], x_auth_token: Optional[str]) -> None:
        required = str(getattr(cfg, "auth_token", "") or "").strip()
        if not required:
            return
        provided = _extract_auth_token(authorization, x_auth_token)
        if not provided or not hmac.compare_digest(required, provided):
            raise HTTPException(status_code=401, detail="invalid auth token")

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        piper_bin = Path(cfg.piper_bin)
        xtts_bin = Path(cfg.xtts_bin)
        return {
            "ok": True,
            "catalog": {
                "piper": len(catalog.get_piper_voices()),
                "xtts_sources": len(catalog.get_xtts_sources()),
            },
            "paths": {
                "tts_root": cfg.tts_root,
                "piper_root": cfg.piper_root,
                "xtts_root": cfg.xtts_root,
            },
            "bootstrap": {
                "on_start": cfg.bootstrap_on_start,
                "download_piper_models": cfg.bootstrap_download_piper_models,
                "models_source_url": cfg.piper_models_source_url,
                "running": bool(bootstrap_state["running"]),
                "error": bootstrap_state["error"],
            },
            "binaries": {
                "piper_bin": cfg.piper_bin,
                "piper_exists": piper_bin.exists() or bool(shutil.which(cfg.piper_bin)),
                "xtts_bin": cfg.xtts_bin,
                "xtts_exists": xtts_bin.exists() or bool(shutil.which(cfg.xtts_bin)),
            },
            "ollama": {
                "tags_endpoint": cfg.ollama_tags_endpoint,
                "chat_endpoint": cfg.ollama_chat_endpoint,
            },
            "cache": wav_cache.stats(),
        }

    @app.get("/tts/voices/piper")
    def get_piper_voices(
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        voices = [asdict(voice) for voice in catalog.get_piper_voices()]
        return {"count": len(voices), "voices": voices}

    @app.get("/tts/voices/xtts")
    def get_xtts_source_voices(
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        voices = [asdict(voice) for voice in catalog.get_xtts_sources()]
        return {"count": len(voices), "voices": voices}

    @app.post("/tts/refresh")
    def refresh_voice_catalog(
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        counts = catalog.refresh()
        return {"ok": True, "counts": counts}

    @app.post("/bootstrap/run")
    def bootstrap_run(
        force: bool = False,
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        report = bootstrap_runtime(cfg, force=force)
        counts = catalog.refresh()
        return {
            "ok": True,
            "bootstrap": report,
            "catalog": counts,
        }

    @app.post("/tts/voices/xtts/upload")
    async def upload_xtts_voice(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
        x_filename: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        max_bytes = int(getattr(cfg, "max_upload_bytes", 25 * 1024 * 1024))
        raw_body = await _read_bounded_body(request, max_bytes)
        raw_name, payload = _extract_upload_part(
            request.headers.get("content-type", ""),
            raw_body,
            x_filename,
        )
        raw_name = str(raw_name or "").strip()
        if not raw_name:
            raise HTTPException(status_code=400, detail="Filename missing")
        if "/" in raw_name or "\\" in raw_name or ".." in raw_name:
            raise HTTPException(status_code=400, detail="Unsafe filename path")
        safe_name = Path(raw_name).name
        if not _SAFE_WAV_NAME_RE.match(safe_name):
            raise HTTPException(status_code=400, detail="Invalid filename (must be safe ASCII ending with .wav)")

        total = len(payload)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"Upload exceeds limit ({max_bytes} bytes)")
        if total <= 0:
            raise HTTPException(status_code=400, detail="Uploaded WAV file is empty")

        xtts_dir = Path(cfg.xtts_root).resolve()
        xtts_dir.mkdir(parents=True, exist_ok=True)
        target_path = (xtts_dir / safe_name).resolve()
        if not target_path.is_relative_to(xtts_dir):
            raise HTTPException(status_code=400, detail="Target path escapes XTTS root")

        tmp_path = target_path.with_name(f"{safe_name}.tmp.{os.getpid()}")
        try:
            with tmp_path.open("wb") as out_f:
                out_f.write(payload)
            os.replace(tmp_path, target_path)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

        counts = catalog.refresh()
        return {"ok": True, "counts": counts, "filename": safe_name, "bytes": total}

    @app.post("/tts/synthesize")
    def synthesize_tts(
        req: SynthesizeRequest,
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ):
        _require_auth(authorization, x_auth_token)
        opts = req.piper if req.engine == "piper" else req.xtts
        wav_bytes, cache_hit = synthesize_cached(
            engine=req.engine,
            text=req.text,
            language=req.language,
            speaker_wav=req.speaker_wav,
            opts=opts,
            catalog=catalog,
            piper_bin=cfg.piper_bin,
            xtts_bin=cfg.xtts_bin,
            cache=wav_cache,
            timeout_sec=float(getattr(cfg, "synth_timeout_sec", 60.0)),
        )
        headers = {"X-Cache": "hit" if cache_hit else "miss"}

        if req.response_format == "json_base64":
            return JSONResponse(
                {
                    "engine": req.engine,
                    "language": req.language,
                    "cached": cache_hit,
                    "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
                },
                headers=headers,
            )

        if req.stream:
            return StreamingResponse(_iter_wav_chunks(wav_bytes), media_type="audio/wav", headers=headers)

        return Response(content=wav_bytes, media_type="audio/wav", headers=headers)

    @app.get("/ollama/tags")
    def get_ollama_tags(
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        try:
            get_fn = getattr(requests, "get", None)
            if getattr(get_fn, "__module__", "") == "requests.api":
                resp = _http_session().get(cfg.ollama_tags_endpoint, timeout=cfg.ollama_timeout_sec)
            else:
                resp = requests.get(cfg.ollama_tags_endpoint, timeout=cfg.ollama_timeout_sec)
            resp.raise_for_status()
            payload = resp.json() if resp.content else {}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch Ollama tags: {exc}") from exc

        return {
            "tags_endpoint": cfg.ollama_tags_endpoint,
            "chat_endpoint": cfg.ollama_chat_endpoint,
            "payload": payload,
        }

    @app.get("/")
    def get_ui():
        static_file = Path(__file__).parent / "static" / "index.html"
        if not static_file.exists():
            return JSONResponse({"ok": True, "message": "UI not built yet"})
        return HTMLResponse(content=static_file.read_text(encoding="utf-8"))

    @app.get("/styles.css")
    def get_css():
        static_file = Path(__file__).parent / "static" / "styles.css"
        if not static_file.exists():
            return Response(status_code=404)
        return Response(content=static_file.read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/script.js")
    def get_js():
        static_file = Path(__file__).parent / "static" / "script.js"
        if not static_file.exists():
            return Response(status_code=404)
        return Response(content=static_file.read_text(encoding="utf-8"), media_type="application/javascript")

    return app


def run_app() -> None:
    import uvicorn

    cfg = load_runtime_config()
    host = str(getattr(cfg, "host", "127.0.0.1") or "127.0.0.1").strip()
    port = int(getattr(cfg, "port", 5000))
    reload_value = str(os.getenv("SENTRYBOT_RELOAD", "0")).strip().lower()
    reload_enabled = reload_value in {"1", "true", "yes", "on"}
    public_bind = host.lower() in {"0.0.0.0", "::", "[::]"}
    if public_bind and not str(getattr(cfg, "auth_token", "") or "").strip():
        raise RuntimeError("SENTRYBOT_TTS_AUTH_TOKEN is required when remote_tts binds to a public interface")

    if reload_enabled:
        target = (
            "services.remote_tts_server.app:app"
            if (Path.cwd() / "services" / "remote_tts_server" / "app.py").exists()
            else "app:app"
        )
        uvicorn.run(target, host=host, port=port, reload=True)
        return

    uvicorn.run(create_app(cfg), host=host, port=port)
