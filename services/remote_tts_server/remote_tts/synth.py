from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .bootstrap import ensure_executable_exists
from .catalog import VoiceCatalog


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


def run_piper_synthesis(
    text: str,
    language: Optional[str],
    piper_opts: Dict[str, Any],
    catalog: VoiceCatalog,
    default_piper_bin: str,
) -> bytes:
    if not text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    resolved_voice = catalog.resolve_piper_voice(language=language, piper_opts=piper_opts)
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
            proc = subprocess.run(
                cmd,
                input=(text.strip() + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
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
) -> bytes:
    if not text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    xtts_bin = ensure_executable_exists(str(xtts_opts.get("bin_path") or default_xtts_bin), "XTTS")
    model_name = str(xtts_opts.get("model_name") or "tts_models/multilingual/multi-dataset/xtts_v2")
    resolved_language = str(language or xtts_opts.get("language") or "tr").strip()
    resolved_speaker = catalog.resolve_xtts_source(explicit_speaker=speaker_wav, xtts_opts=xtts_opts)

    if not resolved_speaker and xtts_opts.get("speaker_idx") is None:
        raise HTTPException(
            status_code=400,
            detail="No XTTS speaker source found. Provide speaker_wav or add source files to XTTS root.",
        )

    extra_args = xtts_opts.get("extra_args")
    if extra_args is None:
        extra_args_list: List[str] = []
    elif isinstance(extra_args, list):
        extra_args_list = [str(item) for item in extra_args]
    else:
        raise HTTPException(status_code=400, detail="xtts.extra_args must be a list")

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
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stderr_txt = proc.stderr.decode("utf-8", errors="ignore").strip()
            if proc.returncode != 0:
                last_err = f"exit={proc.returncode}; stderr={stderr_txt or '<empty>'}"
                continue

            if out_wav.exists() and out_wav.stat().st_size > 0:
                return out_wav.read_bytes()

            last_err = "xtts finished but no output wave file was produced"

        raise HTTPException(status_code=500, detail=f"XTTS synthesis failed: {last_err}")
