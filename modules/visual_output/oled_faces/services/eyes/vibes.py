"""VIBES -- retro full-screen visual loops. When a vibe is active the engine
renders only the vibe painter (eyes are hidden); it stays looping until another
vibe or 'idle' arrives. Painter signature: fn(draw, W, H, now) -> None."""
from __future__ import annotations

import math
import random

_RND = random.Random(0xC0FFEE)          # shared noise source for frame-level randomness
_COL_W, _ROWS, _COLS = 16, 8, 16

# ---- stationary state (single engine thread owns rendering) --------------------
_life_cells = [bool(_RND.random() < 0.42) for _ in range(_ROWS * _COLS)]
_life_gen = 0
_life_grid = [[random.Random(i * 7 + 3).random() for _ in range(24)] for i in range(2)]


def _matrix(d, W, H, t):
    for i in range(_COLS):
        x = i * _COL_W + 4
        speed = 14 + (i * 7 + 3) % 23
        head = ((t * speed + i * 13) % (H + 90)) - 20
        ch = chr(random.Random(int(t * 9) * 31 + i).randrange(0x30A0, 0x30B8))
        d.text((x, head), ch, fill=1)
        for tr in range(3):
            y = head - 10 - tr * 9
            if 0 <= y <= H - 10 and _RND.random() < 0.55 - tr * 0.18:
                d.rectangle([x + _RND.randrange(11), y, x + _RND.randrange(11), y + 2], fill=1)


def _blackhole(d, W, H, t):
    cx, cy = W // 2, H // 2
    for r, seg in ((16, 22), (12, 16)):
        d.arc([cx - r, cy - r, cx + r, cy + r], start=(t * 40) % 360, end=(t * 40) % 360 + seg, fill=1, width=2)
        d.arc([cx - r, cy - r, cx + r, cy + r], start=(t * 40 + 150) % 360, end=(t * 40 + 150) % 360 + seg, fill=1, width=2)
    d.ellipse([cx - 13, cy - 9, cx + 13, cy + 9], fill=1)
    d.ellipse([cx - 9, cy - 6, cx + 9, cy + 6], fill=0)


def _cylon(d, W, H, t):
    mid = 1.0 - abs(1.0 - (t * 0.9) % 2.0)
    x = 6 + mid * (W - 24)
    for back in range(6):
        px = x - (back if x < W // 2 else -back) * 7
        d.rectangle([px, H // 2 - 9, px + 5, H // 2 + 9], fill=1)
        for _ in range(4 - back):
            if _RND.random() < 0.5:
                d.rectangle([px, H // 2 - 9 + _RND.randrange(18), px + 5, H // 2 - 9 + _RND.randrange(18)], fill=0)


def _campfire(d, W, H, t):
    cx = W // 2
    flick = math.sin(t * 9) * 2 + math.sin(t * 17.3) * 1.5
    for layer, (w, y0) in enumerate(((14, 0), (9, 9), (5, 19))):
        d.polygon([(cx - w, H - y0 - 4), (cx + w, H - y0 - 4),
                   (cx + (w // 2 if layer < 2 else 0) + int(flick), H - y0 - 10 - (2 - layer) * 9 - flick),
                   (cx - (w // 2 if layer > 0 else 0) + int(flick), H - y0 - 24)], fill=1)
    for i in range(3):
        f = (t * 0.6 + i / 3) % 1.0
        d.point([cx + (i - 1) * 7 + math.sin(t * 3 + i) * 2, H - 30 - f * (H - 34)], fill=1)
    for x in range(4, W - 4, 2):
        d.point([x, H - 3 + (int(math.sin(x * 0.5 + t * 3)) % 2)], fill=1)


def _game_of_life(d, W, H, t):
    global _life_cells, _life_gen, _life_grid
    if t - _life_gen > 0.35:
        _life_gen = t
        nxt = []
        for r in range(_ROWS):
            for c in range(_COLS):
                n = sum(_life_cells[(r + dr) % _ROWS * _COLS + (c + dc) % _COLS]
                        for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
                nxt.append(n == 3 or (_life_cells[r * _COLS + c] and n == 2))
        _life_cells = nxt
    cw, chh = W / _COLS, H / _ROWS
    for r in range(_ROWS):
        for c in range(_COLS):
            if _life_cells[r * _COLS + c]:
                d.rectangle([c * cw, r * chh, (c + 1) * cw - 1, (r + 1) * chh - 3], fill=1)


def _thermal_scan(d, W, H, t):
    scan = int((t * 0.55 % 1.0) * H)
    bars = [int((math.sin(x * 0.32 + t * 1.6) + math.sin(x * 0.11 - t)) * 4 + H * 0.32) for x in range(0, W, 8)]
    for i, hgt in enumerate(bars):
        x = i * 8
        d.rectangle([x, H - max(2, hgt), x + 5, H - 1], fill=1)
    d.line([(0, scan), (W, scan)], fill=1, width=2)


def _target_lock(d, W, H, t):
    cx, cy = W // 2 + int(math.sin(t * 2.1) * 5), H // 2 + int(math.cos(t * 1.7) * 3)
    r = 17 - (int(t * 3) % 2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=1)
    for rot, seed in ((0, t), (math.pi / 4, t * 1.3)):
        a = (seed * 120 + rot * 57.3) % 360
        d.arc([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], start=a, end=a + 45, fill=1)
    d.line([(cx - 6, cy), (cx + 6, cy)], fill=1)
    d.line([(cx, cy - 6), (cx, cy + 6)], fill=1)
    d.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=1)


def _zen(d, W, H, t):
    ph = (math.sin(t * 0.9) + 1) / 2                     # breath 0..1
    cx, cy = W // 2, H // 2
    r = 6 + ph * 12
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=1, width=2)
    for rip in range(2):
        f = (t * 0.35 + rip / 2) % 1.0
        rr = (r + 2) + f * (10 + 12 * (1 - ph) + rip * 6) * (1 - f)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=1)


VIBES = {
    "matrix": _matrix,
    "blackhole": _blackhole,
    "cylon": _cylon,
    "campfire": _campfire,
    "game_of_life": _game_of_life,
    "thermal_scan": _thermal_scan,
    "target_lock": _target_lock,
    "zen": _zen,
}
