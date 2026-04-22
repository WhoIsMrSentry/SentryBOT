from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse

import requests
from fastapi import HTTPException

from .config import RuntimeConfig

logger = logging.getLogger("remote_tts_server")

PIPER_LINK_REGEX = r"https://huggingface\.co/rhasspy/piper-voices/resolve/[^\"'<>\s]+\.onnx(?:\.json)?\?download=true"


def resolve_executable(path_or_name: str) -> str:
    candidate = Path(path_or_name)
    if candidate.exists():
        return str(candidate)
    found = shutil.which(path_or_name)
    return found or path_or_name


def is_available_executable(path_or_name: str) -> bool:
    resolved = resolve_executable(path_or_name)
    return Path(resolved).exists() or bool(shutil.which(resolved))


def ensure_executable_exists(path_or_name: str, engine_name: str) -> str:
    resolved = resolve_executable(path_or_name)
    if Path(resolved).exists() or shutil.which(resolved):
        return resolved
    raise HTTPException(
        status_code=500,
        detail=f"{engine_name} executable not found: {path_or_name}. Set proper env/bin_path.",
    )


def extract_piper_links(html_text: str) -> List[str]:
    links = re.findall(PIPER_LINK_REGEX, html_text)
    return sorted(set(links))


def relative_path_from_piper_link(url: str) -> Path:
    parsed = urlparse(url)
    marker = "/resolve/"
    path = parsed.path
    index = path.find(marker)
    if index < 0:
        raise ValueError(f"Unexpected piper model URL: {url}")

    tail = path[index + len(marker) :]
    parts = [part for part in tail.split("/") if part]
    if len(parts) < 3:
        raise ValueError(f"Unexpected piper model URL path: {url}")

    rel_parts = parts[1:]
    rel_parts[-1] = unquote(rel_parts[-1])
    return Path(*rel_parts)


def download_file(url: str, target_path: Path, timeout_sec: float) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=timeout_sec, stream=True) as response:
        response.raise_for_status()
        with target_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file_obj.write(chunk)


def bootstrap_piper_models(config: RuntimeConfig, force: bool) -> Dict[str, int]:
    source_url = config.piper_models_source_url
    timeout_sec = config.bootstrap_timeout_sec

    resp = requests.get(source_url, timeout=timeout_sec)
    resp.raise_for_status()
    links = extract_piper_links(resp.text)
    if not links:
        raise RuntimeError(f"No Piper links found at {source_url}")

    downloaded = 0
    skipped = 0
    failed = 0

    for url in links:
        try:
            rel_path = relative_path_from_piper_link(url)
            target_path = Path(config.piper_root) / rel_path
            if target_path.exists() and target_path.stat().st_size > 0 and not force:
                skipped += 1
                continue
            download_file(url, target_path, timeout_sec=timeout_sec)
            downloaded += 1
        except Exception:
            failed += 1

    available_models = sum(1 for _ in Path(config.piper_root).rglob("*.onnx"))
    logger.info(
        "Piper model sync complete | discovered=%d downloaded=%d skipped=%d failed=%d",
        len(links),
        downloaded,
        skipped,
        failed,
    )

    if available_models == 0:
        raise RuntimeError("No Piper .onnx model available after sync")
    if failed > 0:
        logger.warning("Piper sync finished with %d failed file(s)", failed)

    return {
        "discovered": len(links),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "available_models": available_models,
    }


def bootstrap_runtime(config: RuntimeConfig, force: bool = False) -> Dict[str, Any]:
    effective_force = bool(force or config.bootstrap_force)

    Path(config.tts_root).mkdir(parents=True, exist_ok=True)
    Path(config.piper_root).mkdir(parents=True, exist_ok=True)
    Path(config.xtts_root).mkdir(parents=True, exist_ok=True)

    install_report: Dict[str, Any] = {
        "installed": [],
        "already_available": [],
    }

    if config.bootstrap_install_piper:
        if is_available_executable(config.piper_bin) or is_available_executable("piper"):
            install_report["already_available"].append("piper")
        else:
            logger.warning("Piper executable not found! Ensure piper-tts is installed via requirements.txt")

    if config.bootstrap_install_xtts:
        if is_available_executable(config.xtts_bin) or is_available_executable("tts"):
            install_report["already_available"].append("tts")
        else:
            logger.warning("TTS executable not found! Ensure TTS is installed via requirements.txt")

    model_report: Dict[str, Any] = {
        "skipped": True,
    }
    if config.bootstrap_download_piper_models:
        model_report = bootstrap_piper_models(config, force=effective_force)
        model_report["skipped"] = False

    return {
        "install": install_report,
        "piper_models": model_report,
        "force": effective_force,
    }
