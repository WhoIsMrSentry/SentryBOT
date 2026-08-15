#!/usr/bin/env python3
"""Download English (en-us) Vosk model into modules/speech/models/vosk-en."""

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
from typing import List

TARGET = Path(__file__).resolve().parents[2] / "modules" / "speech" / "models" / "vosk-en"

MODEL_URLS: List[str] = [
    "https://huggingface.co/rhasspy/vosk-models/resolve/main/en/vosk-model-small-en-us-0.15.zip",
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
]


def _ssl_context(*, insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _format_bytes(num: int) -> str:
    if num < 1024 * 1024:
        return f"{num / 1024:.1f} KiB"
    return f"{num / (1024 * 1024):.1f} MiB"


def _download(url: str, dest: Path, *, insecure: bool) -> None:
    if insecure:
        try:
            import urllib3  # type: ignore

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    headers = {"User-Agent": "SentryBOT-vosk-install/1.0"}
    try:
        import requests  # type: ignore

        with requests.get(
            url,
            stream=True,
            timeout=(30, 600),
            verify=not insecure,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0) or 0)
            done = 0
            with dest.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        pct = min(100, int(done * 100 / total))
                        print(
                            f"\r  progress: {_format_bytes(done)} / {_format_bytes(total)} ({pct}%)",
                            end="",
                            flush=True,
                        )
            print()
        return
    except ImportError:
        pass

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_ssl_context(insecure=insecure), timeout=600) as resp:
        with dest.open("wb") as handle:
            shutil.copyfileobj(resp, handle)


def _try_urls(urls: List[str], dest: Path, *, insecure: bool) -> str:
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
    parser = argparse.ArgumentParser(description="Install English Vosk model (en-us small)")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS verification (use on Pi if alphacephei cert fails)",
    )
    args = parser.parse_args(argv)
    insecure = bool(args.insecure or os.getenv("VOSK_INSTALL_INSECURE", "").strip().lower() in {"1", "true", "yes"})

    if TARGET.is_dir() and any(TARGET.iterdir()):
        print(f"OK: model already present at {TARGET}")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if insecure:
        print("NOTE: TLS verification disabled for this run.", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "vosk-en.zip"
        used_url = _try_urls(MODEL_URLS, zpath, insecure=insecure)
        _install_from_zip(zpath)

    print(f"Installed Vosk EN model at {TARGET}")
    print(f"Source: {used_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
