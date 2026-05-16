#!/usr/bin/env python3
"""Download Turkish Vosk model into modules/speech/models/vosk-tr."""

from __future__ import annotations

import argparse
import os
import shutil
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, List

TARGET = Path(__file__).resolve().parents[1] / "modules" / "speech" / "models" / "vosk-tr"

# Primary + mirrors (HuggingFace often has valid TLS when alphacephei cert is stale on Pi).
MODEL_URLS: List[str] = [
    "https://alphacephei.com/vosk/models/vosk-model-small-tr-0.22.zip",
    "https://huggingface.co/rhasspy/vosk-models/resolve/main/tr/vosk-model-small-tr-0.3.zip",
]


def _ssl_context(*, insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _download(url: str, dest: Path, *, insecure: bool) -> None:
    headers = {"User-Agent": "SentryBOT-vosk-install/1.0"}
    try:
        import requests  # type: ignore

        resp = requests.get(url, stream=True, timeout=300, verify=not insecure, headers=headers)
        resp.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)
        return
    except ImportError:
        pass

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_ssl_context(insecure=insecure), timeout=300) as resp:
        with dest.open("wb") as handle:
            shutil.copyfileobj(resp, handle)


def _try_urls(urls: Iterable[str], dest: Path, *, insecure: bool) -> str:
    last_error: Exception | None = None
    for url in urls:
        try:
            print(f"Downloading {url} ...")
            _download(url, dest, insecure=insecure)
            return url
        except Exception as exc:
            last_error = exc
            print(f"  failed: {exc}", file=sys.stderr)
    if last_error is not None:
        raise last_error
    raise RuntimeError("no download URLs configured")


def _install_from_zip(zpath: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(work)
        extracted = next(work.glob("vosk-model-*"), None)
        if extracted is None or not extracted.is_dir():
            raise RuntimeError("unexpected zip layout (expected vosk-model-* directory)")
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.move(str(extracted), str(TARGET))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Turkish Vosk model for speech/STT")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification (use if Pi CA bundle is outdated)",
    )
    args = parser.parse_args(argv)
    insecure = bool(args.insecure or os.getenv("VOSK_INSTALL_INSECURE", "").strip().lower() in {"1", "true", "yes"})

    if TARGET.is_dir() and any(TARGET.iterdir()):
        print(f"OK: model already present at {TARGET}")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)

    if insecure:
        print("WARNING: downloading with TLS verification disabled.", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "vosk-tr.zip"
        used_url = _try_urls(MODEL_URLS, zpath, insecure=insecure)
        _install_from_zip(zpath)

    print(f"Installed Vosk TR model at {TARGET} (from {used_url})")
    if insecure:
        print(
            "Tip: fix Pi certificates with: sudo apt update && sudo apt install -y ca-certificates",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
