from __future__ import annotations

import base64
import logging
import os
import shutil
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.responses import JSONResponse, Response, HTMLResponse

from .bootstrap import bootstrap_runtime
from .catalog import VoiceCatalog
from .config import RuntimeConfig, load_runtime_config
from .models import SynthesizeRequest
from .synth import run_piper_synthesis, run_xtts_synthesis

logger = logging.getLogger("remote_tts_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def create_app(runtime_cfg: Optional[RuntimeConfig] = None) -> FastAPI:
    cfg = runtime_cfg or load_runtime_config()
    catalog = VoiceCatalog(
        piper_root=Path(cfg.piper_root),
        xtts_root=Path(cfg.xtts_root),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if cfg.bootstrap_on_start:
            bootstrap_info = bootstrap_runtime(cfg, force=False)
            logger.info("Runtime bootstrap finished: %s", bootstrap_info)
        catalog.refresh()
        yield

    app = FastAPI(title="SentryBOT Remote TTS Server", version="0.1.0", lifespan=lifespan)

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
        if _extract_auth_token(authorization, x_auth_token) != required:
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
        }

    @app.get("/tts/voices/piper")
    def get_piper_voices(authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        voices = [asdict(voice) for voice in catalog.get_piper_voices()]
        return {"count": len(voices), "voices": voices}

    @app.get("/tts/voices/xtts")
    def get_xtts_source_voices(authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        voices = [asdict(voice) for voice in catalog.get_xtts_sources()]
        return {"count": len(voices), "voices": voices}

    @app.post("/tts/refresh")
    def refresh_voice_catalog(authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        counts = catalog.refresh()
        return {"ok": True, "counts": counts}

    @app.post("/bootstrap/run")
    def bootstrap_run(force: bool = False, authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        report = bootstrap_runtime(cfg, force=force)
        counts = catalog.refresh()
        return {
            "ok": True,
            "bootstrap": report,
            "catalog": counts,
        }

    @app.post("/tts/voices/xtts/upload")
    async def upload_xtts_voice(file: UploadFile = File(...), authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _require_auth(authorization, x_auth_token)
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename missing")
        if not file.filename.lower().endswith(".wav"):
            raise HTTPException(status_code=400, detail="Only .wav files are supported")
            
        xtts_dir = Path(cfg.xtts_root)
        xtts_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = xtts_dir / file.filename
        content = await file.read()
        target_path.write_bytes(content)
        
        counts = catalog.refresh()
        return {"ok": True, "counts": counts, "filename": file.filename}

    @app.post("/tts/synthesize")
    def synthesize_tts(req: SynthesizeRequest, authorization: Optional[str] = Header(default=None), x_auth_token: Optional[str] = Header(default=None)):
        _require_auth(authorization, x_auth_token)
        if req.engine == "piper":
            wav_bytes = run_piper_synthesis(
                text=req.text,
                language=req.language,
                piper_opts=req.piper,
                catalog=catalog,
                default_piper_bin=cfg.piper_bin,
            )
        elif req.engine == "xtts":
            wav_bytes = run_xtts_synthesis(
                text=req.text,
                language=req.language,
                speaker_wav=req.speaker_wav,
                xtts_opts=req.xtts,
                catalog=catalog,
                default_xtts_bin=cfg.xtts_bin,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported engine: {req.engine}")

        if req.response_format == "json_base64":
            return JSONResponse(
                {
                    "engine": req.engine,
                    "language": req.language,
                    "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
                }
            )

        return Response(content=wav_bytes, media_type="audio/wav")

    @app.get("/ollama/tags")
    def get_ollama_tags() -> Dict[str, Any]:
        try:
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

    uvicorn.run("app:app", host=host, port=port, reload=reload_enabled)
