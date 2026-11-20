"""Download and optionally INT8-quantize offline TR<->EN NMT models (Opus-MT -> CTranslate2).

Run on Raspberry Pi 5 or Windows when internet is available so HybridTranslator
has zero-LLM offline fallback weights ready under `models/translate/`.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from typing import Tuple

DEFAULT_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("tr", "en", "Helsinki-NLP/opus-mt-tr-en"),
    ("en", "tr", "Helsinki-NLP/opus-mt-tc-big-en-tr"),
)


def install_pair(src: str, tgt: str, hf_repo: str, out_root: Path, quant: str = "int8") -> Path:
    dest = out_root / f"{src}-{tgt}"
    if (dest / "model.bin").is_file() or (dest / "config.json").is_file():
        print(f"[skip] {src}->{tgt} already exists at {dest}")
        return dest

    dest.mkdir(parents=True, exist_ok=True)
    ct2_ok = False
    try:
        import ctranslate2  # noqa: F401
        from ctranslate2.converters import TransformersConverter  # type: ignore

        tmp_dir = out_root / f"_tmp_{src}_{tgt}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        converter = TransformersConverter(hf_repo)
        converter.convert(str(dest), quantization=quant, force=True)
        # Copy tokenizer assets next to model.bin so Offline backend loads offline
        from huggingface_hub import snapshot_download  # type: ignore

        snap = Path(
            snapshot_download(
                hf_repo,
                allow_patterns=["*.spm", "*vocab*", "*tokenizer*", "config.json"],
            )
        )
        for item in snap.iterdir():
            if item.is_file() and item.suffix in {".spm", ".json", ".txt"}:
                shutil.copy2(item, dest / item.name)
        ct2_ok = True
        print(f"[ok] CTranslate2 ({quant}) model ready: {dest}")
    except Exception as exc:
        print(f"[info] CTranslate2 conversion unavailable ({exc}); saving HuggingFace Opus-MT instead")

    if not ct2_ok:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # type: ignore

        tok = AutoTokenizer.from_pretrained(hf_repo)
        model = AutoModelForSeq2SeqLM.from_pretrained(hf_repo)
        tok.save_pretrained(str(dest))
        model.save_pretrained(str(dest))
        print(f"[ok] HuggingFace offline model saved: {dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install offline TR<->EN translation models")
    parser.add_argument("--out-dir", default="models/translate", help="Target directory for offline models")
    parser.add_argument("--quant", default="int8", help="CTranslate2 quantization (int8, int8_float16, float32)")
    args = parser.parse_args(argv)

    out_root = Path(args.out_dir)
    for src, tgt, repo in DEFAULT_PAIRS:
        install_pair(src, tgt, repo, out_root, quant=args.quant)
    return 0


if __name__ == "__main__":
    sys.exit(main())
