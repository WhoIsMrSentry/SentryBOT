"""Low-level drawing helpers + eased-approach math, shared by every eye layer."""
from __future__ import annotations

import math

_PI = math.pi


def ease(cur, tgt, dt, tau):
    """Frame-rate-independent exponential approach of cur -> tgt."""
    return tgt + (cur - tgt) * math.exp(-dt / tau)


def rounded_rect(d, x, y, w, h, r, fill):
    """rounded_rectangle with clamped radius (thin/blinking eyes never raise)."""
    if w <= 0 or h <= 0:
        return
    x0, y0, x1, y1 = round(x), round(y), round(x + w - 1), round(y + h - 1)
    if x1 < x0 or y1 < y0:
        return
    rr = max(0, min(int(r), (x1 - x0) // 2, (y1 - y0) // 2))
    if rr <= 0:
        d.rectangle([x0, y0, x1, y1], fill=fill)
    else:
        d.rounded_rectangle([x0, y0, x1, y1], radius=rr, fill=fill)


def heart(d, cx, cy, s):
    """Smooth parametric heart centred at (cx, cy), ~s px wide."""
    sc = s / 33.0
    pts = [(cx + 16 * math.sin(t) ** 3 * sc,
            cy - (13 * math.cos(t) - 5 * math.cos(2 * t)
                  - 2 * math.cos(3 * t) - math.cos(4 * t)) * sc + 2 * sc)
           for t in (i * math.pi / 18 for i in range(36))]
    d.polygon(pts, fill=1)


def sparkle(d, cx, cy, s):
    """4-point twinkle centred at (cx, cy)."""
    R, r = s, s * 0.34
    pts = [(cx + (R if k % 2 == 0 else r) * math.cos(-_PI / 2 + k * _PI / 4),
            cy + (R if k % 2 == 0 else r) * math.sin(-_PI / 2 + k * _PI / 4))
           for k in range(8)]
    d.polygon(pts, fill=1)


def draw_formula(d, x, y, text):
    """Draw a short formula; a '^' raises the next char as a superscript."""
    cx = x
    for k, ch in enumerate(text):
        if ch == "^":
            continue
        sup = k > 0 and text[k - 1] == "^"
        d.text((cx, y - 3 if sup else y), ch, fill=1)
        cx += 4 if sup else 6
