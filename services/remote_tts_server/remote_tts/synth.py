from __future__ import annotations

from collections import OrderedDict
import io
import json
import logging
import re
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .bootstrap import ensure_executable_exists
from .catalog import VoiceCatalog

logger = logging.getLogger("remote_tts_server.synth")

_ALLOWED_XTTS_FLAGS = frozenset({
    "--use_deepspeed",
    "--enable_text_splitting",
    "--split_sentences",
    "--temperature",
    "--length_penalty",
    "--repetition_penalty",
    "--top_k",
    "--top_p",
    "--speed",
})
_UNSAFE_ARG_RE = re.compile(r"[;&|`$><\r\n]")

_PIPER_PYTHON_CACHE: Dict[str, Any] = {}
_XTTS_PYTHON_CACHE: Dict[str, Any] = {}
_BACKEND_CACHE_LOCK = threading.Lock()


class WavLRUCache:
    """Thread-safe bounded LRU cache mapping normalized synthesis requests to WAV bytes."""

    def __init__(self, max_entries: int = 32) -> None:
        self.max_entries = max(0, int(max_entries))
        self._lock = threading.Lock()
        self._data: "OrderedDict[str, bytes]" = OrderedDict()

    @staticmethod
    def make_key(
        engine: str,
        text: str,
        language: Optional[str],
        speaker_wav: Optional[str],
        opts: Dict[str, Any],
    ) -> str:
        return json.dumps(
            {
                "engine": engine,
                "text": text.strip(),
                "language": str(language or "").strip().lower(),
                "speaker_wav": str(speaker_wav or "").strip(),
                "opts": opts,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def get(self, key: str) -> Optional[bytes]:
        if self.max_entries <= 0:
            return None
        with self._lock:
            val = self._data.get(key)
            if val is None:
                return None
            self._data.move_to_end(key)
            return val

    def put(self, key: str, wav_bytes: bytes) -> None:
        if self.max_entries <= 0 or not wav_bytes:
            return
        with self._lock:
            self._data[key] = wav_bytes
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"entries": len(self._data), "max_entries": self.max_entries}


def _validate_xtts_extra_args(extra_args: Any) -> List[str]:
    if extra_args is None:
        return []
    if not isinstance(extra_args, list):
        raise HTTPException(status_code=400, detail="xtts.extra_args must be a list")
    cleaned: List[str] = []
    expect_value = False
    for raw in extra_args:
        item = str(raw).strip()
        if not item or _UNSAFE_ARG_RE.search(item):
            raise HTTPException(status_code=400, detail=f"Unsafe extra_args token: {raw!r}")
        if item.startswith("-"):
            flag = item.split("=", 1)[0]
            if flag not in _ALLOWED_XTTS_FLAGS:
                raise HTTPException(status_code=400, detail=f"Disallowed xtts extra arg: {flag}")
            cleaned.append(item)
            expect_value = "=" not in item and flag in {
                "--temperature",
                "--length_penalty",
                "--repetition_penalty",
                "--top_k",
                "--top_p",
                "--speed",
            }
        elif expect_value:
            cleaned.append(item)
            expect_value = False
        else:
            raise HTTPException(status_code=400, detail=f"Unexpected positional extra_args token: {item}")
    return cleaned


def _append_piper_common_options(base_cmd: List[str], piper_opts: Dict[str, Any], config_path: Optional[str]) -> List[str]:
    cmd = list(base_cmd)
    if config_path:
        cmd += ["--config", config_path]
    if piper_opts.get("speaker") is not None:
        cmd += ["--speaker", str(piper_opts.get("speaker"))]
    if piper_opts.get("length_scale") is not None:
        cmd += ["--length_scale", str(piper_opts.get("length_scale"))]
    if piper_opts.get("noise_scale") is not None:
        cmd += ["--noise_scale", str(piper_opts.get("noise_scale"))]
    if piper_opts.get("noise_w") is not None:
        cmd += ["--noise_w", str(piper_opts.get("noise_w"))]
    return cmd


def _append_piper_short_options(base_cmd: List[str], piper_opts: Dict[str, Any]) -> List[str]:
    cmd = list(base_cmd)
    if piper_opts.get("speaker") is not None:
        cmd += ["-s", str(piper_opts.get("speaker"))]
    if piper_opts.get("length_scale") is not None:
        cmd += ["-l", str(piper_opts.get("length_scale"))]
    if piper_opts.get("noise_scale") is not None:
        cmd += ["-n", str(piper_opts.get("noise_scale"))]
    if piper_opts.get("noise_w") is not None:
        cmd += ["-e", str(piper_opts.get("noise_w"))]
    return cmd


def _try_inprocess_piper(
    text: str,
    model_path: str,
    config_path: Optional[str],
    piper_opts: Dict[str, Any],
) -> Optional[bytes]:
    """Use cached in-process PiperVoice when piper-tts Python module is installed."""
    try:
        from piper.voice import PiperVoice  # type: ignore
    except Exception:
        return None
    with _BACKEND_CACHE_LOCK:
        voice = _PIPER_PYTHON_CACHE.get(model_path)
        if voice is None:
            voice = PiperVoice.load(model_path, config_path=config_path)
            _PIPER_PYTHON_CACHE[model_path] = voice
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        kwargs: Dict[str, Any] = {}
        if piper_opts.get("speaker") is not None:
            kwargs["speaker_id"] = int(piper_opts["speaker"])
        if piper_opts.get("length_scale") is not None:
            kwargs["length_scale"] = float(piper_opts["length_scale"])
        if piper_opts.get("noise_scale") is not None:
            kwargs["noise_scale"] = float(piper_opts["noise_scale"])
        if piper_opts.get("noise_w") is not None:
            kwargs["noise_w"] = float(piper_opts["noise_w"])
        voice.synthesize(text.strip(), wf, **kwargs)
    return buf.getvalue()


def _try_inprocess_xtts(
    text: str,
    model_name: str,
    language: str,
    speaker_wav: Optional[str],
    xtts_opts: Dict[str, Any],
) -> Optional[bytes]:
    """Use cached Coqui TTS model in-process when TTS Python package is available."""
    try:
        from TTS.api import TTS  # type: ignore
    except Exception:
        return None
    with _BACKEND_CACHE_LOCK:
        tts_obj = _XTTS_PYTHON_CACHE.get(model_name)
        if tts_obj is None:
            tts_obj = TTS(model_name=model_name)
            _XTTS_PYTHON_CACHE[model_name] = tts_obj
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_wav = Path(tmp_dir) / "xtts_cached.wav"
        kwargs: Dict[str, Any] = {"text": text, "file_path": str(out_wav)}
        if language:
            kwargs["language"] = language
        if speaker_wav:
            kwargs["speaker_wav"] = speaker_wav
        elif xtts_opts.get("speaker_idx") is not None:
            kwargs["speaker"] = str(xtts_opts["speaker_idx"])
        tts_obj.tts_to_file(**kwargs)
        if out_wav.exists() and out_wav.stat().st_size > 0:
            return out_wav.read_bytes()
    return None


def run_piper_synthesis(
    text: str,
    language: Optional[str],
    piper_opts: Dict[str, Any],
    catalog: VoiceCatalog,
    default_piper_bin: str,
    timeout_sec: float = 60.0,
) -> bytes:
    if not text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    resolved_voice = catalog.resolve_piper_voice(language=language, piper_opts=piper_opts)
    cached_bytes = _try_inprocess_piper(text, resolved_voice.model_path, resolved_voice.config_path, piper_opts)
    if cached_bytes is not None:
        return cached_bytes

    piper_bin = ensure_executable_exists(str(piper_opts.get("bin_path") or default_piper_bin), "Piper")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_wav = Path(tmp_dir) / "out.wav"
        model_path = resolved_voice.model_path
        cmd_variants = [
            _append_piper_common_options(
                [piper_bin, "--model", model_path, "--output_file", str(out_wav)],
                piper_opts,
                resolved_voice.config_path,
            ),
            _append_piper_short_options([piper_bin, "-m", model_path, "-w", str(out_wav)], piper_opts),
        ]

        last_err = "unknown piper failure"
        for cmd in cmd_variants:
            try:
                proc = subprocess.run(
                    cmd,
                    input=(text.strip() + "\n").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_sec,
                )
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=504, detail=f"Piper synthesis timed out after {timeout_sec}s") from exc

            stderr_txt = proc.stderr.decode("utf-8", errors="ignore").strip()
            if proc.returncode != 0:
                last_err = f"exit={proc.returncode}; stderr={stderr_txt or '<empty>'}"
                continue

            if out_wav.exists() and out_wav.stat().st_size > 0:
                return out_wav.read_bytes()

            if proc.stdout:
                return proc.stdout

            last_err = "piper finished but no audio output was produced"

        raise HTTPException(status_code=500, detail=f"Piper synthesis failed: {last_err}")


def run_xtts_synthesis(
    text: str,
    language: Optional[str],
    speaker_wav: Optional[str],
    xtts_opts: Dict[str, Any],
    catalog: VoiceCatalog,
    default_xtts_bin: str,
    timeout_sec: float = 60.0,
) -> bytes:
    if not text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    model_name = str(xtts_opts.get("model_name") or "tts_models/multilingual/multi-dataset/xtts_v2")
    resolved_language = str(language or xtts_opts.get("language") or "tr").strip()
    resolved_speaker = catalog.resolve_xtts_source(explicit_speaker=speaker_wav, xtts_opts=xtts_opts)

    if not resolved_speaker and xtts_opts.get("speaker_idx") is None:
        raise HTTPException(
            status_code=400,
            detail="No XTTS speaker source found. Provide speaker_wav or add source files to XTTS root.",
        )

    extra_args_list = _validate_xtts_extra_args(xtts_opts.get("extra_args"))
    if not extra_args_list and not xtts_opts.get("bin_path"):
        inproc = _try_inprocess_xtts(text, model_name, resolved_language, resolved_speaker, xtts_opts)
        if inproc is not None:
            return inproc

    xtts_bin = ensure_executable_exists(str(xtts_opts.get("bin_path") or default_xtts_bin), "XTTS")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_wav = Path(tmp_dir) / "xtts_out.wav"

        base_cmd = [
            xtts_bin,
            "--text",
            text,
            "--model_name",
            model_name,
            "--out_path",
            str(out_wav),
        ]
        if resolved_speaker:
            base_cmd += ["--speaker_wav", resolved_speaker]
        if xtts_opts.get("speaker_idx") is not None:
            base_cmd += ["--speaker_idx", str(xtts_opts.get("speaker_idx"))]
        base_cmd += extra_args_list

        command_variants = []
        if resolved_language:
            command_variants.append(base_cmd + ["--language_idx", resolved_language])
            command_variants.append(base_cmd + ["--language", resolved_language])
        else:
            command_variants.append(base_cmd)

        last_err = "unknown xtts failure"
        for cmd in command_variants:
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_sec,
                )
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=504, detail=f"XTTS synthesis timed out after {timeout_sec}s") from exc

            stderr_txt = proc.stderr.decode("utf-8", errors="ignore").strip()
            if proc.returncode != 0:
                last_err = f"exit={proc.returncode}; stderr={stderr_txt or '<empty>'}"
                continue

            if out_wav.exists() and out_wav.stat().st_size > 0:
                return out_wav.read_bytes()

            last_err = "xtts finished but no output wave file was produced"

        raise HTTPException(status_code=500, detail=f"XTTS synthesis failed: {last_err}")


def synthesize_cached(
    *,
    engine: str,
    text: str,
    language: Optional[str],
    speaker_wav: Optional[str],
    opts: Dict[str, Any],
    catalog: VoiceCatalog,
    piper_bin: str,
    xtts_bin: str,
    cache: WavLRUCache,
    timeout_sec: float = 60.0,
) -> Tuple[bytes, bool]:
    """Synthesize WAV audio via cache lookup -> engine execution -> cache store."""
    cache_key = cache.make_key(engine, text, language, speaker_wav, opts)
    hit = cache.get(cache_key)
    if hit is not None:
        return hit, True

    if engine == "piper":
        wav_bytes = run_piper_synthesis(
            text=text,
            language=language,
            piper_opts=opts,
            catalog=catalog,
            default_piper_bin=piper_bin,
            timeout_sec=timeout_sec,
        )
    elif engine == "xtts":
        wav_bytes = run_xtts_synthesis(
            text=text,
            language=language,
            speaker_wav=speaker_wav,
            xtts_opts=opts,
            catalog=catalog,
            default_xtts_bin=xtts_bin,
            timeout_sec=timeout_sec,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported engine: {engine}")

    cache.put(cache_key, wav_bytes)
    return wav_bytes, False
