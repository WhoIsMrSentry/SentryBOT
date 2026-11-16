#!/usr/bin/env python3
"""Download Piper ONNX voices (Turkish + GLaDOS) into data/piper_models/."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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


def compute_sha256(path: Path, chunk_bytes: int = 1024 * 512) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def verify_sha256(path: Path, expected_sha256: Optional[str]) -> bool:
    """Verify SHA256 digest when an expected hash is provided; returns True if valid or unpinned."""
    expected = str(expected_sha256 or "").strip().lower()
    if not expected:
        return True
    actual = compute_sha256(path)
    return actual == expected


def _load_sha256_manifest(manifest_path: Optional[Path] = None) -> Dict[str, str]:
    """Load optional relpath -> sha256 overrides from checksums.json or config/model_assets.json."""
    out: Dict[str, str] = {}
    candidates = []
    if manifest_path is not None:
        candidates.append(manifest_path)
    candidates.extend([TARGET_ROOT / "checksums.json", REPO_ROOT / "config" / "model_assets.json"])
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            # Support flat map {"tr_TR-.../....onnx": "<hex>"}
            for k, v in data.items():
                if isinstance(v, str) and len(v.strip()) == 64:
                    out[str(k)] = v.strip().lower()
            # Support model_assets.json nested assets specs with model_sha256 / config_sha256
            assets = data.get("assets")
            if isinstance(assets, dict):
                for spec in assets.values():
                    if not isinstance(spec, dict):
                        continue
                    if spec.get("model_path") and spec.get("model_sha256"):
                        out[str(Path(spec["model_path"]).name)] = str(spec["model_sha256"]).strip().lower()
                    if spec.get("config_path") and spec.get("config_sha256"):
                        out[str(Path(spec["config_path"]).name)] = str(spec["config_sha256"]).strip().lower()
    return out


def _validate_downloaded_artifact(
    path: Path,
    expected_sha256: Optional[str] = None,
    *,
    is_json: Optional[bool] = None,
) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise ValueError(f"Downloaded file is empty: {path}")
    check_json = is_json if is_json is not None else (path.suffix == ".json" or ".json." in path.name)
    if check_json:
        json.loads(path.read_text(encoding="utf-8"))
    if not verify_sha256(path, expected_sha256):
        actual = compute_sha256(path)
        raise ValueError(f"SHA256 mismatch for {path.name}: expected={expected_sha256} actual={actual}")


def _download(
    url: str,
    dest: Path,
    *,
    insecure: bool,
    expected_sha256: Optional[str] = None,
) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        if expected_sha256 and not verify_sha256(dest, expected_sha256):
            print(f"  re-download (SHA256 mismatch): {dest.relative_to(REPO_ROOT)}")
        else:
            if dest.suffix == ".json":
                json.loads(dest.read_text(encoding="utf-8"))
            print(f"  skip (exists): {dest.relative_to(REPO_ROOT)}")
            return compute_sha256(dest)

    if insecure:
        try:
            import urllib3  # type: ignore

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    headers = {"User-Agent": "SentryBOT-piper-install/1.0"}
    print(f"  download: {url}")
    tmp_path = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
    try:
        downloaded = False
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
                with tmp_path.open("wb") as handle:
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
                downloaded = True
        except ImportError:
            pass

        if not downloaded:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=_ssl_context(insecure=insecure), timeout=900) as resp:
                with tmp_path.open("wb") as handle:
                    shutil.copyfileobj(resp, handle)

        _validate_downloaded_artifact(
            tmp_path,
            expected_sha256=expected_sha256,
            is_json=(dest.suffix == ".json"),
        )
        tmp_path.replace(dest)
        sha_hex = compute_sha256(dest)
        sidecar = dest.with_name(dest.name + ".sha256")
        sidecar.write_text(f"{sha_hex}  {dest.name}\n", encoding="utf-8")
        return sha_hex
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def _install_pack(
    name: str,
    files: Iterable[VoiceFile],
    *,
    insecure: bool,
    checksums: Optional[Dict[str, str]] = None,
) -> None:
    print(f"\n=== {name} ===")
    cs = checksums or {}
    for url, rel in files:
        dest = TARGET_ROOT / rel
        expected = cs.get(rel) or cs.get(dest.name)
        try:
            sha_hex = _download(url, dest, insecure=insecure, expected_sha256=expected)
            print(f"  sha256: {sha_hex[:16]}... ({dest.name})")
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
    parser.add_argument("--checksum-manifest", default=None, help="Optional JSON file mapping filenames to SHA256 digests")
    parser.add_argument("--verify", action="store_true", help="Verify existing files against checksum manifest/sidecars")
    args = parser.parse_args(argv)
    insecure = bool(args.insecure or os.getenv("PIPER_INSTALL_INSECURE", "").strip().lower() in {"1", "true", "yes"})

    packs = _select_packs(args)
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    checksums = _load_sha256_manifest(Path(args.checksum_manifest) if args.checksum_manifest else None)

    if insecure:
        print("NOTE: TLS verification disabled.", file=sys.stderr)

    print(f"Target directory: {TARGET_ROOT}")
    if args.verify:
        for pack in packs:
            for _url, rel in VOICE_PACKS[pack]:
                dest = TARGET_ROOT / rel
                expected = checksums.get(rel) or checksums.get(dest.name)
                if not dest.exists():
                    print(f"  MISSING: {rel}", file=sys.stderr)
                    return 2
                _validate_downloaded_artifact(dest, expected_sha256=expected)
                print(f"  OK: {rel} (sha256={compute_sha256(dest)[:16]}...)")
        return 0

    for pack in packs:
        _install_pack(pack, VOICE_PACKS[pack], insecure=insecure, checksums=checksums)

    print("\nDone. Set speak.tts.engine=piper and voice paths in config/agent.yaml")
    print("Default Turkish: data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx")
    print("GLaDOS:          data/piper_models/en-glados-medium/glados_piper_medium.onnx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
