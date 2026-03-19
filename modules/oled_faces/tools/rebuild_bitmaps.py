from __future__ import annotations

from pathlib import Path
import argparse


def decode_page_buffer(raw: bytes, width: int, height: int) -> list[list[int]]:
    buf = [[0 for _ in range(width)] for _ in range(height)]
    pages = height // 8
    for p in range(pages):
        row_base = p * width
        for x in range(width):
            b = raw[row_base + x]
            for bit in range(8):
                y = p * 8 + bit
                if y < height:
                    buf[y][x] = 1 if (b & (1 << bit)) else 0
    return buf


def encode_page_buffer(buf: list[list[int]], width: int, height: int) -> bytes:
    out = bytearray((width * height) // 8)
    pages = height // 8
    for p in range(pages):
        row_base = p * width
        for x in range(width):
            b = 0
            for bit in range(8):
                y = p * 8 + bit
                if y < height and buf[y][x]:
                    b |= 1 << bit
            out[row_base + x] = b
    return bytes(out)


def center_crop(src: list[list[int]], src_w: int, src_h: int, dst_w: int, dst_h: int) -> list[list[int]]:
    x0 = max(0, (src_w - dst_w) // 2)
    y0 = max(0, (src_h - dst_h) // 2)
    out = [[0 for _ in range(dst_w)] for _ in range(dst_h)]
    for y in range(dst_h):
        sy = min(src_h - 1, y0 + y)
        for x in range(dst_w):
            sx = min(src_w - 1, x0 + x)
            out[y][x] = src[sy][sx]
    return out


def nearest_resize(src: list[list[int]], src_w: int, src_h: int, dst_w: int, dst_h: int) -> list[list[int]]:
    out = [[0 for _ in range(dst_w)] for _ in range(dst_h)]
    for y in range(dst_h):
        sy = min(src_h - 1, int(round(y * (src_h - 1) / max(1, dst_h - 1))))
        for x in range(dst_w):
            sx = min(src_w - 1, int(round(x * (src_w - 1) / max(1, dst_w - 1))))
            out[y][x] = src[sy][sx]
    return out


def infer_height(byte_len: int, width: int) -> int:
    # page-buffer size = width * height / 8
    h = (byte_len * 8) // width
    if h <= 0 or (width * h) // 8 != byte_len:
        raise ValueError(f"cannot infer source height from size={byte_len} width={width}")
    return h


def rebuild(in_dir: Path, out_dir: Path, src_w: int, src_h: int | None, dst_w: int, dst_h: int, mode: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(in_dir.glob("*.bin"))
    if not files:
        raise FileNotFoundError(f"no .bin files found in {in_dir}")

    for fp in files:
        raw = fp.read_bytes()
        sh = src_h if src_h is not None else infer_height(len(raw), src_w)
        expect = (src_w * sh) // 8
        if len(raw) < expect:
            raw = raw + (b"\x00" * (expect - len(raw)))
        elif len(raw) > expect:
            raw = raw[:expect]

        src = decode_page_buffer(raw, src_w, sh)
        if mode == "resize":
            dst = nearest_resize(src, src_w, sh, dst_w, dst_h)
        else:
            dst = center_crop(src, src_w, sh, dst_w, dst_h)
        out = encode_page_buffer(dst, dst_w, dst_h)
        (out_dir / fp.name).write_bytes(out)


def main() -> None:
    p = argparse.ArgumentParser(description="Rebuild OLED page-buffer bitmaps for target panel size")
    p.add_argument("--in-dir", default="modules/oled_faces/assets/bitmaps")
    p.add_argument("--out-dir", default="modules/oled_faces/assets/bitmaps_128x32")
    p.add_argument("--src-width", type=int, default=128)
    p.add_argument("--src-height", type=int, default=64)
    p.add_argument("--dst-width", type=int, default=128)
    p.add_argument("--dst-height", type=int, default=32)
    p.add_argument("--mode", choices=["crop", "resize"], default="crop")
    args = p.parse_args()

    rebuild(
        Path(args.in_dir),
        Path(args.out_dir),
        src_w=int(args.src_width),
        src_h=int(args.src_height) if int(args.src_height) > 0 else None,
        dst_w=int(args.dst_width),
        dst_h=int(args.dst_height),
        mode=str(args.mode),
    )
    print(f"rebuilt bitmaps -> {args.out_dir}")


if __name__ == "__main__":
    main()
