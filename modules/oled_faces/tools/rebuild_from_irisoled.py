from __future__ import annotations

import argparse
import re
from pathlib import Path


HEX_RE = re.compile(r"0x[0-9A-Fa-f]{2}")


def parse_header_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8", errors="ignore")
    vals = [int(x, 16) for x in HEX_RE.findall(text)]
    return bytes(vals)


def decode_xbm_rows_lsb(raw: bytes, width: int, height: int) -> list[list[int]]:
    row_bytes = width // 8
    need = row_bytes * height
    if len(raw) < need:
        raw = raw + (b"\x00" * (need - len(raw)))
    elif len(raw) > need:
        raw = raw[:need]

    pix = [[0 for _ in range(width)] for _ in range(height)]
    for y in range(height):
        base = y * row_bytes
        for xb in range(row_bytes):
            b = raw[base + xb]
            x0 = xb * 8
            for bit in range(8):
                if b & (1 << bit):
                    pix[y][x0 + bit] = 1
    return pix


def downscale_binary_or(src: list[list[int]], src_w: int, src_h: int, dst_w: int, dst_h: int) -> list[list[int]]:
    # Fast path for 128x64 -> 128x32 using 2-row OR (keeps details on small panel)
    if src_w == dst_w and src_h == dst_h * 2:
        out = [[0 for _ in range(dst_w)] for _ in range(dst_h)]
        for y in range(dst_h):
            y0 = y * 2
            y1 = y0 + 1
            row0 = src[y0]
            row1 = src[y1]
            for x in range(dst_w):
                out[y][x] = 1 if (row0[x] or row1[x]) else 0
        return out

    # Generic nearest for other shapes
    out = [[0 for _ in range(dst_w)] for _ in range(dst_h)]
    for y in range(dst_h):
        sy = min(src_h - 1, int(round(y * (src_h - 1) / max(1, dst_h - 1))))
        for x in range(dst_w):
            sx = min(src_w - 1, int(round(x * (src_w - 1) / max(1, dst_w - 1))))
            out[y][x] = src[sy][sx]
    return out


def encode_page_buffer(pix: list[list[int]], width: int, height: int) -> bytes:
    out = bytearray((width * height) // 8)
    pages = height // 8
    for p in range(pages):
        base = p * width
        for x in range(width):
            b = 0
            for bit in range(8):
                y = p * 8 + bit
                if y < height and pix[y][x]:
                    b |= 1 << bit
            out[base + x] = b
    return bytes(out)


def to_name(path: Path) -> str:
    return path.stem.strip().lower().replace(" ", "_") + ".bin"


def build(irisoled_root: Path, out_dir: Path, src_w: int, src_h: int, dst_w: int, dst_h: int) -> int:
    eye_dir = irisoled_root / "extras" / "eye expressions" / "bitmap arrays"
    special_dir = irisoled_root / "extras" / "special expressions" / "bitmap arrays"

    headers = []
    if eye_dir.exists():
        headers.extend(sorted(eye_dir.glob("*.h")))
    if special_dir.exists():
        headers.extend(sorted(special_dir.glob("*.h")))

    if not headers:
        raise FileNotFoundError(f"No bitmap headers found under {irisoled_root}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for hp in headers:
        raw = parse_header_bytes(hp)
        pix = decode_xbm_rows_lsb(raw, src_w, src_h)
        small = downscale_binary_or(pix, src_w, src_h, dst_w, dst_h)
        out = encode_page_buffer(small, dst_w, dst_h)
        (out_dir / to_name(hp)).write_bytes(out)
        written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild OLED bins from Irisoled C header arrays")
    ap.add_argument("--irisoled-root", default="modules/oled_faces/tools/_irisoled_src")
    ap.add_argument("--out-dir", default="modules/oled_faces/assets/bitmaps_128x32_clean")
    ap.add_argument("--src-width", type=int, default=128)
    ap.add_argument("--src-height", type=int, default=64)
    ap.add_argument("--dst-width", type=int, default=128)
    ap.add_argument("--dst-height", type=int, default=32)
    args = ap.parse_args()

    count = build(
        Path(args.irisoled_root),
        Path(args.out_dir),
        int(args.src_width),
        int(args.src_height),
        int(args.dst_width),
        int(args.dst_height),
    )
    print(f"generated {count} bitmap(s) into {args.out_dir}")


if __name__ == "__main__":
    main()
