#!/usr/bin/env python3
"""Download Piper ONNX voices (Turkish + GLaDOS) into data/piper_models/."""

from __future__ import annotations

import argparse
import os
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = REPO_ROOT / "data" / "piper_models"

# rhasspy/piper-voices v1.0.0 + DavesArmoury GLaDOS Piper export
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
GLADOS_BASE = "https://huggingface.co/DavesArmoury/GLaDOS_TTS/resolve/main"

VoiceFile = Tuple[str, str]  # (url, relative path under TARGET_ROOT)

VOICE_PACKS: Dict[str, List[VoiceFile]] = {
    "tr-dfki": [
        (f"{HF_BASE}/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx", "tr_TR-dfki-medium/tr_TR-dfki-medium.onnx"),
        (
            f"{HF_BASE}/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx.json",
            "tr_TR-dfki-medium/tr_TR-dfki-medium.onnx.json",
        ),
    ],
    "tr-fahrettin": [
        (
            f"{HF_BASE}/tr/tr_TR/fahrettin/medium/tr_TR-fahrettin-medium.onnx",
            "tr_TR-fahrettin-medium/tr_TR-fahrettin-medium.onnx",
        ),
        (
            f"{HF_BASE}/tr/tr_TR/fahrettin/medium/tr_TR-fahrettin-medium.onnx.json",
            "tr_TR-fahrettin-medium/tr_TR-fahrettin-medium.onnx.json",
        ),
    ],
    "tr-fettah": [
        (
            f"{HF_BASE}/tr/tr_TR/fettah/medium/tr_TR-fettah-medium.onnx",
            "tr_TR-fettah-medium/tr_TR-fettah-medium.onnx",
        ),
        (
            f"{HF_BASE}/tr/tr_TR/fettah/medium/tr_TR-fettah-medium.onnx.json",
            "tr_TR-fettah-medium/tr_TR-fettah-medium.onnx.json",
        ),
    ],
    "glados": [
        (f"{GLADOS_BASE}/glados_piper_medium.onnx", "en-glados-medium/glados_piper_medium.onnx"),
        (f"{GLADOS_BASE}/glados_piper_medium.onnx.json", "en-glados-medium/glados_piper_medium.onnx.json"),
    ],
}

TURKISH_PACKS = ("tr-dfki", "tr-fahrettin", "tr-fettah")


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
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest.relative_to(REPO_ROOT)}")
        return

    if insecure:
        try:
            import urllib3  # type: ignore

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    headers = {"User-Agent": "SentryBOT-piper-install/1.0"}
    print(f"  download: {url}")
    try:
        import requests  # type: ignore

        with requests.get(
            url,
            stream=True,
            timeout=(30, 900),
            verify=not insecure,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0) or 0)
            done = 0
            with dest.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        pct = min(100, int(done * 100 / total))
                        print(
                            f"\r    {_format_bytes(done)} / {_format_bytes(total)} ({pct}%)",
                            end="",
                            flush=True,
                        )
            print()
        return
    except ImportError:
        pass

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_ssl_context(insecure=insecure), timeout=900) as resp:
        with dest.open("wb") as handle:
            shutil.copyfileobj(resp, handle)


def _install_pack(name: str, files: Iterable[VoiceFile], *, insecure: bool) -> None:
    print(f"\n=== {name} ===")
    for url, rel in files:
        dest = TARGET_ROOT / rel
        try:
            _download(url, dest, insecure=insecure)
        except Exception as exc:
            print(f"  FAILED {rel}: {exc}", file=sys.stderr)
            raise


def _select_packs(args: argparse.Namespace) -> List[str]:
    if args.all:
        return list(VOICE_PACKS.keys())
    packs: List[str] = []
    if args.turkish:
        packs.extend(TURKISH_PACKS)
    if args.glados:
        packs.append("glados")
    if args.pack:
        for name in args.pack:
            if name not in VOICE_PACKS:
                raise SystemExit(f"Unknown pack: {name} (choose from {', '.join(VOICE_PACKS)})")
            packs.append(name)
    if not packs:
        packs = ["tr-dfki", "glados"]
    return list(dict.fromkeys(packs))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Piper voice models for SentryBOT TTS")
    parser.add_argument("--turkish", action="store_true", help="All Turkish voices (dfki, fahrettin, fettah)")
    parser.add_argument("--glados", action="store_true", help="GLaDOS English Piper voice")
    parser.add_argument("--all", action="store_true", help="Turkish + GLaDOS")
    parser.add_argument(
        "--pack",
        action="append",
        metavar="NAME",
        help=f"Single pack: {', '.join(VOICE_PACKS.keys())}",
    )
    parser.add_argument("--insecure", action="store_true", help="Skip TLS certificate verification")
    args = parser.parse_args(argv)
    insecure = bool(args.insecure or os.getenv("PIPER_INSTALL_INSECURE", "").strip().lower() in {"1", "true", "yes"})

    packs = _select_packs(args)
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    if insecure:
        print("NOTE: TLS verification disabled.", file=sys.stderr)

    print(f"Target directory: {TARGET_ROOT}")
    for pack in packs:
        _install_pack(pack, VOICE_PACKS[pack], insecure=insecure)

    print("\nDone. Set speak.tts.engine=piper and voice paths in config/agent.yaml")
    print("Default Turkish: data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx")
    print("GLaDOS:          data/piper_models/en-glados-medium/glados_piper_medium.onnx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
