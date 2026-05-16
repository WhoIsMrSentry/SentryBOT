#!/usr/bin/env python3
"""Download Turkish Vosk model into modules/speech/models/vosk-tr."""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-tr-0.22.zip"
TARGET = Path(__file__).resolve().parents[1] / "modules" / "speech" / "models" / "vosk-tr"


def main() -> int:
    if TARGET.is_dir() and any(TARGET.iterdir()):
        print(f"OK: model already present at {TARGET}")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_URL} ...")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "vosk-tr.zip"
        urllib.request.urlretrieve(MODEL_URL, zpath)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(tmp)
        extracted = next(Path(tmp).glob("vosk-model-*"), None)
        if extracted is None or not extracted.is_dir():
            print("ERROR: unexpected zip layout", file=sys.stderr)
            return 1
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.move(str(extracted), str(TARGET))
    print(f"Installed Vosk TR model at {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
