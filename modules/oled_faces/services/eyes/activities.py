"""ACTIVITIES -- a looping "what I'm doing" status: a gaze pose + an overlay icon.
Each busy activity also wears a fitting face (see ACT_MOOD)."""
from __future__ import annotations

import itertools
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .primitives import draw_formula, frame, rand, smoothstep

ACTIVITIES = (
    "idle", "thinking", "scanning", "searching", "processing", "working", "editing",
    "debugging", "building", "testing", "deploying", "connecting", "ping_pong",
    "listening", "waiting", "glitch",
)
ACT_MOOD = {
    "thinking": "focused", "scanning": "neutral", "searching": "focused",
    "working": "focused", "listening": "neutral", "editing": "smoking",
    "processing": "focused", "connecting": "attentive",
    "debugging": "suspicious", "building": "focused", "testing": "focused",
    "deploying": "neutral", "ping_pong": "scared", "waiting": "bored", "glitch": "scared",
}

# Self-ending activities: glitch rolls out after ~3s windows (50% chance per window).
_GLITCH_ROLL_S = 3.0
_GLITCH_HEAL_ODD = 0.5


def _glitch_expired(now: float, start: float) -> bool:
    k = int((now - start) / _GLITCH_ROLL_S)
    return k >= 1 and rand(start + k * 7.31) < _GLITCH_HEAL_ODD


ACT_EXPIRY = {"glitch": _glitch_expired}

# ping_pong sonar timeline
_PP_OUT, _PP_HOLD, _PP_SEG = 1.3, 0.6, 1.9
_PP_CYCLE = 2 * _PP_SEG
_PP_MAXR, _PP_HMULT = 150, 0.6

# deploying sea spectrum (built once)
def _make_spectrum():
    waves = []
    for i in range(7):
        k = 2 * math.pi / (15 + rand(i) * 90)
        waves.append((k, math.sqrt(5.0 * k) * (0.9 + 0.2 * rand(i + 13)),
                      rand(i + 23) * 6.283, 0.25 + 0.8 * rand(i + 7)))
    return waves


_SPECTRUM = _make_spectrum()

# waiting terminal script
_WAIT_WORD = "waiting"
_WAIT_PROMPT = "> "
_WAIT_FULL = _WAIT_WORD + "..."
_WAIT_WIN, _WAIT_CHANCE, _WAIT_BLINK, _WAIT_CURW = 5.0, 0.7, 1.0, 6
_WAIT_DOT, _WAIT_DOT_REPS, _WAIT_DEL = 0.42, 2, 0.05
_WAIT_DELAYS = tuple(0.07 + 0.06 * (1.0 + math.sin(i * 1.7)) for i in range(len(_WAIT_WORD)))
_WAIT_CUM = tuple(itertools.accumulate(_WAIT_DELAYS))
_WAIT_TYPE_DUR = _WAIT_CUM[-1]
_WAIT_DOTS_DUR = _WAIT_DOT_REPS * 3 * _WAIT_DOT
_WAIT_DEL_DUR = len(_WAIT_FULL) * _WAIT_DEL
_WAIT_ACT_DUR = _WAIT_TYPE_DUR + _WAIT_DOTS_DUR + _WAIT_DEL_DUR

# glitch corruption beats
_GLITCH_BEAT, _GLITCH_AMP = 0.07, 6


def pose(act, now):
    """Eased gaze target (x, y) + height multiplier for a looping activity."""
    if act == "thinking":
        return math.sin(now * 0.7) * 7, -9 + math.sin(now * 0.4) * 2, 1.0
    if act == "scanning":
        line = now * 1.0
        return (int(line % 1.0 * 4) / 3 * 2 - 1) * 13, (int(line) % 3 - 1) * 5, 1.0
    if act == "searching":
        return math.sin(now * 2.2) * 11 + math.sin(now * 1.3) * 5, math.sin(now * 1.7) * 5, 1.0
    if act == "working":
        return math.sin(now * 1.6) * 5, 4 + math.sin(now * 0.8) * 1, 0.85
    if act == "listening":
        return math.sin(now * 1.8) * 2, math.sin(now * 3.6) * 2, 1.0
    if act == "processing":
        return math.sin(now * 1.4) * 4, -2 + math.sin(now * 0.7), 0.92
    if act == "connecting":
        return math.sin(now * 1.5) * 3, math.sin(now * 2.0) * 2, 1.0
    if act == "debugging":
        return math.sin(now * 1.4) * 12 + math.sin(now * 3.1) * 3, 5 + math.sin(now * 4.0), 0.9
    if act == "building":
        return math.sin(now * 1.5) * 1.5, 4 + math.sin(now * 2.0) * 1.5, 0.92
    if act == "testing":
        return 5 + math.sin(now * 1.6) * 1.5, 5 + math.sin(now * 1.1) * 1.5, 0.95
    if act == "deploying":
        return math.sin(now * 0.25) * 4, 7 + math.sin(now * 1.7) * 1.2, 1.0
    if act == "ping_pong":
        return ((-6.0, -4.0, _PP_HMULT) if (now % _PP_CYCLE) < _PP_SEG
                else (6.0, 4.0, _PP_HMULT))
    if act == "waiting":
        return math.sin(now * 0.4) * 2, 2 + math.sin(now * 0.6), 1.0
    if act == "glitch":
        f = int(now / _GLITCH_BEAT) % len(_GLITCH_BEATS)
        if _GLITCH_BEATS[f] is None:
            return 0.0, 0.0, 1.0
        jx, jy = rand(f), rand(f, 7)
        return (round(jx * 4) - 2) * 3, (round(jy * 2) - 1) * 2, 1.0
    return 0.0, 0.0, 1.0


# ---- overlay icons: drawn on top of the eyes. Signature: (d, W, H, now) --------
def _think(d, W, H, now):
    tokens = ("E=mc^2", "a^2+b^2=c^2", "F=ma", "v=d/t", "2^10", "i^2=-1", "dx/dt",
              "3.14", "1.618", "9.8", "42", "404", "1337", "O(n)", "?")
    for i in range(4):
        t = (now * 0.4 + i / 4) % 1.0
        y = H - 10 - t * (H - 16)
        ti = (i * 3 + int(now * 0.4 + i / 4)) % len(tokens)
        x = 6 + i * (W - 50) / 3 + math.sin(now * 1.1 + i * 2) * 5
        draw_formula(d, x, y, tokens[ti])


def _headphones(d, W, H, now):
    cw, ch = 11, 22
    cy = H // 2 - ch // 2
    d.rounded_rectangle([2, cy, 2 + cw, cy + ch], radius=4, fill=1)
    d.rounded_rectangle([W - 3 - cw, cy, W - 3, cy + ch], radius=4, fill=1)
    d.arc([8, 1, W - 9, H - 12], start=180, end=360, fill=1, width=3)


def _magnifier(d, W, H, now):
    rad = 6
    cx = W / 2 + math.sin(now * 1.6) * (W / 2 - 12)
    cy = H - 11 + math.sin(now * 3.2) * 2
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=1, width=2)
    hx, hy = cx + rad * 0.7, cy + rad * 0.7
    d.line([hx, hy, hx + 5, hy + 5], fill=1, width=2)


def _hammer(d, W, H, now):
    ax, ay = W // 2 + 4, H - 6
    px, py = ax - 6, H - 18
    raised, struck = math.radians(-38), math.radians(82)
    t = (now * 0.8) % 1.0
    th = (struck + (raised - struck) * (t / 0.7) if t < 0.7
          else raised + (struck - raised) * ((t - 0.7) / 0.3))
    hx, hy = px + 12 * math.cos(th), py + 12 * math.sin(th)
    nx, ny = -math.sin(th), math.cos(th)
    d.line([px, py, hx, hy], fill=1, width=2)
    d.line([hx - 6 * nx, hy - 6 * ny, hx + 6 * nx, hy + 6 * ny], fill=1, width=5)
    d.rectangle([ax - 7, ay, ax + 7, ay + 3], fill=1)
    if t < 0.25:
        s = 1.0 - t / 0.25
        L = 5 + 11 * s
        for k in range(5):
            a = math.radians(-160 + k * 35)
            d.line([ax, ay - 1, ax + math.cos(a) * L, ay - 1 + math.sin(a) * L], fill=1, width=2)


def _typing(d, W, H, now):
    base = H - 3
    for i, cx in enumerate((18, W - 18)):
        tap = round((math.sin(now * 8 + i * math.pi) + 1) / 2 * 3)
        cy = base - 6 + tap
        thumb = cx + (7 if i == 0 else -7)
        d.ellipse([thumb - 2, cy - 3, thumb + 3, cy + 2], fill=1)
        d.rounded_rectangle([cx - 7, cy - 5, cx + 7, cy + 2], radius=3, fill=1)
        for k in range(4):
            fx = cx - 5 + k * 4
            d.ellipse([fx - 2, cy, fx + 2, cy + 5], fill=1)
        for k in range(3):
            nx = cx - 3 + k * 4
            d.line([nx, cy + 1, nx, cy + 5], fill=0, width=1)


def _arc_ring(d, W, H, now):
    cx, cy, rad = W // 2, H - 11, 8
    a0 = int(now * 200) % 360
    d.arc([cx - rad, cy - rad, cx + rad, cy + rad], start=a0, end=a0 + 210, fill=1, width=2)


def _link_dots(d, W, H, now):
    cy = H - 11
    for i in range(3):
        t = (math.sin(now * 4 - i * 1.1) + 1) / 2
        s = 1.5 + 2.5 * t
        x = W / 2 - 10 + i * 10
        d.ellipse([x - s / 2, cy - s / 2, x + s / 2, cy + s / 2], fill=1)


def _debug_bug(d, W, H, now):
    cx = W / 2 + math.sin(now * 1.4) * (W / 2 - 14)
    cy = H - 8
    face = 1 if math.cos(now * 1.4) >= 0 else -1
    d.ellipse([cx - 6, cy - 4, cx + 6, cy + 4], fill=1)
    hx = cx + face * 6
    d.ellipse([hx - 2, cy - 2, hx + 2, cy + 2], fill=1)
    d.line([cx, cy - 4, cx, cy + 4], fill=0, width=1)
    for k in (-1, 1):
        for j in range(3):
            px = cx - 4 + j * 4
            wig = math.sin(now * 14 + j + (k + 1)) * 1.5
            d.line([px, cy + k * 3, px + wig, cy + k * 6], fill=1, width=1)
    d.line([hx, cy - 1, hx + face * 3, cy - 4], fill=1, width=1)
    d.line([hx, cy + 1, hx + face * 3, cy - 2], fill=1, width=1)


def _cube(d, cx, cy, s):
    h, o = s / 2, s * 0.42
    x0, y0, x1, y1 = cx - h, cy - h, cx + h, cy + h
    d.polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill=1, outline=0)
    d.polygon([(x0, y0), (x0 + o, y0 - o), (x1 + o, y0 - o), (x1, y0)], fill=1, outline=0)
    d.polygon([(x1, y0), (x1 + o, y0 - o), (x1 + o, y1 - o), (x1, y1)], fill=1, outline=0)


def _building(d, W, H, now):
    s, step, hold, fall, gap = 10, 0.5, 0.15, 0.6, 0.2
    asm = 3 * step
    T = asm + hold + fall + gap
    cyc, lp = int(now / T), now % T
    cx = W / 2
    slot_y = (H - 9, H - 9 - (s + 2), H - 9 - 2 * (s + 2))
    for i in range(3):
        ty = slot_y[i]
        if lp < asm:
            start = i * step
            if lp < start:
                continue
            k = smoothstep(min(1.0, (lp - start) / step))
            dirn = int(rand(cyc * 9.7 + i * 4.3) * 3)
            sx, sy = (-14, ty) if dirn == 0 else (W + 14, ty) if dirn == 1 else (cx, -14)
            x, y = sx + (cx - sx) * k, sy + (ty - sy) * k
        elif lp < asm + hold:
            x, y = cx, ty
        else:
            tc = (lp - asm - hold) / fall
            x, y = cx + (i - 1) * (38 + i * 12) * tc, ty + 70 * tc * tc
        _cube(d, x, y, s)


def _testing(d, W, H, now):
    env = lambda n, thr, soft: max(0.0, min(1.0, (n - thr) / soft))
    shake = env(math.sin(now * 0.8) + math.sin(now * 1.9 + 1.0), 0.85, 0.3)
    bubl = env(math.sin(now * 0.5 + 0.7) + math.sin(now * 1.27 + 2.4), -0.2, 0.55)
    gasl = env(math.sin(now * 0.41) + math.sin(now * 0.93 + 1.6), 0.65, 0.5)
    jx = math.sin(now * 42) * 2.0 * shake
    cx, top, bot, hw = W - 10 + jx, H - 30, H - 4, 5
    liq = top + 11
    d.line([cx - hw, top, cx - hw, bot - hw], fill=1)
    d.line([cx + hw, top, cx + hw, bot - hw], fill=1)
    d.arc([cx - hw, bot - 2 * hw, cx + hw, bot], start=0, end=180, fill=1)
    d.rectangle([cx - hw + 1, liq, cx + hw - 1, bot - hw], fill=1)
    d.ellipse([cx - hw + 1, bot - 2 * hw, cx + hw - 1, bot], fill=1)
    d.rectangle([cx - hw - 1, top - 4, cx + hw + 1, top], fill=1)
    d.line([cx - hw - 1, top - 2, cx + hw + 1, top - 2], fill=0)
    for i in range(3):
        bt = (now * (0.6 + i * 0.17) + i * 0.31) % 1.0
        by = (bot - hw) - bt * (bot - hw - liq)
        bx = cx + math.sin(now * 3 + i * 2) * (hw - 2.5)
        r = (0.8 + (i % 2)) * bubl
        if r > 0.45:
            d.ellipse([bx - r, by - r, bx + r, by + r], fill=0)
    if gasl > 0.05:
        for mx, wdt, spd, off in ((cx - 2, 1, 0.33, 0.0), (cx + 3, 2, 0.25, 0.55)):
            p = (now * spd + off) % 1.0
            ln = (3 + min(p / 0.82, 1.0) * 21) * gasl
            lift = max(0.0, (p - 0.82) / 0.18) * (ln + 8)
            pts = [(mx + math.sin(f * 3.6 + now * 1.8) * (0.5 + f * 2.6), (top - 4 - lift) - f * ln)
                   for f in (j / 7 for j in range(8))]
            d.line(pts, fill=1, width=wdt, joint="curve")


def _deploying(d, W, H, now):
    sea_at = lambda t: max(0.0, min(1.0, 0.5 + 0.34 * math.sin(t * 0.06) + 0.16 * math.sin(t * 0.015 + 1.3)))
    sea, wl = sea_at(now), H - 4
    amp = 0.4 + sea
    height = lambda x: sum(ba * amp * math.sin(k * x - w * now + ph) for k, w, ph, ba in _SPECTRUM)
    surf = lambda x: wl + height(x)
    berth = W / 2 + (sea_at(now - 3.0) - 0.5) * 34
    cx = berth + sum(ba * amp * math.cos(k * berth - w * now + ph) for k, w, ph, ba in _SPECTRUM) * 0.5
    sy = surf(cx)
    pitch = math.degrees(math.atan(sum(ba * amp * k * math.cos(k * cx - w * now + ph)
                                       for k, w, ph, ba in _SPECTRUM))) * 0.45
    lay = Image.new("1", (W, H), 0)
    g = ImageDraw.Draw(lay)
    deck = sy - 11
    g.chord([cx - 24, deck - 13, cx + 16, deck + 13], 0, 180, fill=1)
    g.polygon([(cx + 10, deck + 1), (cx + 22, deck - 10), (cx + 16, deck + 1)], fill=1)
    g.polygon([(cx + 15, deck - 6), (cx + 24, deck - 3), (cx + 16, deck + 1)], fill=1)
    cw, ch, scx = 8, 4, cx - 5
    for r, n in enumerate((4, 3, 1)):
        x0, yt = scx - n * cw / 2, deck - (r + 1) * ch
        for c in range(n):
            bx = x0 + c * cw
            g.rectangle([bx, yt, bx + cw, yt + ch], fill=1, outline=0)
    g.ellipse([cx - 20, deck - 3, cx - 18, deck - 1], fill=0)
    lay = lay.rotate(pitch, resample=Image.NEAREST, center=(cx, sy))
    belly = [(x, surf(x)) for x in range(0, W + 1, 2)] + [(W, H), (0, H)]
    ImageDraw.Draw(lay).polygon(belly, fill=0)
    base = frame(d)
    if base is not None:
        base.paste(0, (0, 0), lay.convert("L").filter(ImageFilter.MaxFilter(3)).convert("1"))
        base.paste(1, (0, 0), lay)
    d.line([(x, surf(x)) for x in range(0, W + 1, 2)], fill=1, width=1, joint="curve")


def _sonar(d, cx, cy, a0, a1, prog):
    lead = smoothstep(prog) * _PP_MAXR
    for off, w in ((0, 2), (11, 2), (50, 1)):
        r = lead - off
        if r > 2:
            d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=1, width=w)


def _contact(d, x, y, now):
    s = 1.5 + (math.sin(now * 6) * 0.5 + 0.5) * 2
    d.ellipse([x - s, y - s, x + s, y + s], fill=1)


def _ping_pong(d, W, H, now):
    t = now % _PP_CYCLE
    if t < _PP_SEG:
        d.text((W - 30, 2), "PING", fill=1)
        _contact(d, W - 4, 6, now)
        if t < _PP_OUT:
            _sonar(d, 0, 0, 0, 90, t / _PP_OUT)
    else:
        d.text((9, H - 12), "PONG", fill=1)
        _contact(d, 4, H - 7, now)
        local = t - _PP_SEG
        if local < _PP_OUT:
            _sonar(d, W - 1, H - 1, 180, 270, local / _PP_OUT)


def _wait_speaks(bucket):
    return rand(bucket + 1) < _WAIT_CHANCE


def _wait_script(now):
    if not _wait_speaks(int(now / _WAIT_WIN)):
        return "", "blink"
    t = now % _WAIT_WIN
    if t >= _WAIT_ACT_DUR:
        return "", "blink"
    if t < _WAIT_TYPE_DUR:
        return _WAIT_WORD[:sum(t >= c for c in _WAIT_CUM)], "solid"
    t -= _WAIT_TYPE_DUR
    if t < _WAIT_DOTS_DUR:
        return _WAIT_WORD + "." * (int(t / _WAIT_DOT) % 3 + 1), "off"
    t -= _WAIT_DOTS_DUR
    return _WAIT_FULL[:len(_WAIT_FULL) - int(t / _WAIT_DEL) - 1], "solid"


def _waiting(d, W, H, now):
    text, mode = _wait_script(now)
    y = H - 11
    line = _WAIT_PROMPT + text
    tw = d.textlength(line) if hasattr(d, "textlength") else len(line) * 6
    x = round(W / 2 - (tw + _WAIT_CURW) / 2)
    d.text((x, y - 1), line, fill=1)
    if mode == "solid" or (mode == "blink" and (now % _WAIT_BLINK) < _WAIT_BLINK / 2):
        d.rectangle([x + tw + 1, y + 8, x + tw + _WAIT_CURW, y + 9], fill=1)


def _datamosh(d, img, W, H, t, seed, amp):
    if img is None:
        return
    for k in range(3):
        y = (seed * 13 + k * 29) % (H - 4)
        h = 2 + (seed + k) % 4
        dx = (seed * 7 + k * 17) % (2 * amp + 1) - amp
        strip = img.crop((0, y, W, y + h))
        img.paste(0, (0, y, W, y + h))
        img.paste(strip, (dx, y))


def _displace_blocks(d, img, W, H, t, seed, amp):
    if img is None:
        return
    for k in range(2):
        bw, bh = 16 + (seed * 5 + k * 11) % 22, 6 + (seed * 3 + k * 7) % 12
        x = (seed * 9 + k * 23) % max(1, W - bw)
        y = (seed * 4 + k * 19) % max(1, H - bh)
        dx = (seed * 7 + k * 13) % (2 * amp + 1) - amp
        img.paste(img.crop((x, y, x + bw, y + bh)), (x + dx, y))


def _scanlines(d, img, W, H, t, seed, amp):
    for y in range(seed % 3, H, 3):
        d.line([0, y, W, y], fill=0, width=1)
    u, by = 4, int(abs(math.sin(seed * 0.13)) * (H // 4)) * 4
    for c in range(W // u):
        if rand(c, seed) > 0.5:
            d.rectangle([c * u, by, c * u + u - 1, by + u - 1], fill=1)


def _ghost(d, img, W, H, t, seed, amp):
    if img is None:
        return
    img.paste(ImageChops.lighter(img, ImageChops.offset(img, amp, 0)), (0, 0))


def _code_rain(d, img, W, H, t, seed, amp):
    for col in range(6):
        x = 6 + col * (W - 12) // 5
        head = (t * (20 + (seed + col * 7) % 14) + col * 3.3) % (H + 10) - 5
        for j in range(4):
            y = int(head - j * 5)
            if 0 <= y < H:
                d.line([x, y, x, y + 3], fill=1, width=1)


def _invert_flash(d, img, W, H, t, seed, amp):
    if img is None:
        return
    img.paste(ImageChops.invert(img.convert("L")).convert("1"), (0, 0))


_GLITCH_BEATS = (_datamosh, _scanlines, None, _displace_blocks, _code_rain, None,
                 _datamosh, _ghost, _invert_flash, None, _displace_blocks, _scanlines,
                 None, _code_rain, _datamosh, None, _ghost, _displace_blocks, None,
                 _scanlines, _datamosh, None)


def _glitch(d, W, H, now):
    f = int(now / _GLITCH_BEAT) % len(_GLITCH_BEATS)
    effect = _GLITCH_BEATS[f]
    if effect:
        effect(d, frame(d), W, H, now, f * 7 + 1, _GLITCH_AMP)


OVERLAYS = {
    "thinking": _think, "searching": _magnifier, "working": _hammer,
    "listening": _headphones, "processing": _arc_ring, "connecting": _link_dots,
    "editing": _typing, "debugging": _debug_bug, "building": _building,
    "testing": _testing, "deploying": _deploying, "ping_pong": _ping_pong,
    "waiting": _waiting, "glitch": _glitch,
}
