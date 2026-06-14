"""ACTIVITIES -- a looping "what I'm doing" status: a gaze pose + an overlay icon.
Each busy activity also wears a fitting face (see ACT_MOOD)."""
from __future__ import annotations

import math

from .primitives import draw_formula

ACTIVITIES = ("idle", "thinking", "scanning", "searching", "working", "listening",
              "processing", "connecting")
# each busy activity wears a fitting face; listening just stays attentive (neutral)
ACT_MOOD = {"thinking": "focused", "scanning": "neutral", "searching": "focused",
            "working": "focused", "listening": "neutral",
            "processing": "focused", "connecting": "attentive"}


def pose(act, now):
    """Eased gaze target (x, y) + height multiplier for a looping activity."""
    if act == "thinking":   # gaze up at the floating symbols, slow wander
        return math.sin(now * 0.7) * 7, -9 + math.sin(now * 0.4) * 2, 1.0
    if act == "scanning":   # step left->right then down a line, settling each stop
        line = now * 1.0
        return (int(line % 1.0 * 4) / 3 * 2 - 1) * 13, (int(line) % 3 - 1) * 5, 1.0
    if act == "searching":  # quick wandering glances -- scanning results
        return math.sin(now * 2.2) * 11 + math.sin(now * 1.3) * 5, math.sin(now * 1.7) * 5, 1.0
    if act == "working":    # heads-down on the task, hammering away below
        return math.sin(now * 1.6) * 5, 4 + math.sin(now * 0.8) * 1, 0.85
    if act == "listening":  # attentive, gently nodding along under the headphones
        return math.sin(now * 1.8) * 2, math.sin(now * 3.6) * 2, 1.0
    if act == "processing": # locked-in, computing -- a tight steady focus
        return math.sin(now * 1.4) * 4, -2 + math.sin(now * 0.7), 0.92
    if act == "connecting": # expectant, waiting on the link
        return math.sin(now * 1.5) * 3, math.sin(now * 2.0) * 2, 1.0
    return 0.0, 0.0, 1.0


# ---- overlay icons: drawn on top of the eyes. Signature: (d, W, H, now) --------
def _think(d, W, H, now):
    # formulas, numbers & nerdy easter eggs drift up -- pondering ('^' raises next char)
    # 42 = the Answer; 404 = not found; 1337 = leet; O(n) = big-O.
    tokens = ("E=mc^2", "a^2+b^2=c^2", "F=ma", "v=d/t", "2^10", "i^2=-1", "dx/dt",
              "3.14", "1.618", "9.8", "42", "404", "1337", "O(n)", "?")
    for i in range(4):
        t = (now * 0.4 + i / 4) % 1.0                   # 0..1 rise progress
        y = H - 10 - t * (H - 16)                       # float up the screen
        ti = (i * 3 + int(now * 0.4 + i / 4)) % len(tokens)
        x = 6 + i * (W - 50) / 3 + math.sin(now * 1.1 + i * 2) * 5
        draw_formula(d, x, y, tokens[ti])


def _headphones(d, W, H, now):
    # cute headphones: a band over the top + an ear cup each side -- "listening"
    cw, ch = 11, 22
    cy = H // 2 - ch // 2
    d.rounded_rectangle([2, cy, 2 + cw, cy + ch], radius=4, fill=1)          # left cup
    d.rounded_rectangle([W - 3 - cw, cy, W - 3, cy + ch], radius=4, fill=1)  # right cup
    d.arc([8, 1, W - 9, H - 12], start=180, end=360, fill=1, width=3)        # headband


def _magnifier(d, W, H, now):
    # a magnifying glass sweeps across -- "searching / looking things up"
    rad = 6
    cx = W / 2 + math.sin(now * 1.6) * (W / 2 - 12)
    cy = H - 11 + math.sin(now * 3.2) * 2
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=1, width=2)  # lens rim
    hx, hy = cx + rad * 0.7, cy + rad * 0.7
    d.line([hx, hy, hx + 5, hy + 5], fill=1, width=2)                        # handle


def _hammer(d, W, H, now):
    # "getting work done": a hammer winds up slow and strikes an anvil hard, big sparks
    ax, ay = W // 2 + 4, H - 6                        # anvil strike point
    px, py = ax - 6, H - 18                           # wrist pivot, above-left
    raised, struck = math.radians(-38), math.radians(82)
    t = (now * 0.8) % 1.0                             # slow, deliberate rhythm
    th = (struck + (raised - struck) * (t / 0.7) if t < 0.7      # long slow wind-up
          else raised + (struck - raised) * ((t - 0.7) / 0.3))   # snap down to strike
    hx, hy = px + 12 * math.cos(th), py + 12 * math.sin(th)
    nx, ny = -math.sin(th), math.cos(th)             # crossbar dir, perpendicular to handle
    d.line([px, py, hx, hy], fill=1, width=2)        # handle
    d.line([hx - 6 * nx, hy - 6 * ny, hx + 6 * nx, hy + 6 * ny], fill=1, width=5)  # head
    d.rectangle([ax - 7, ay, ax + 7, ay + 3], fill=1)  # anvil / work piece
    if t < 0.25:                                      # impact: strong spark, fades on recoil
        s = 1.0 - t / 0.25                            # 1 right after the hit -> 0
        L = 5 + 11 * s
        for k in range(5):                            # upward fan of sparks
            a = math.radians(-160 + k * 35)
            d.line([ax, ay - 1, ax + math.cos(a) * L, ay - 1 + math.sin(a) * L], fill=1, width=2)


def _arc_ring(d, W, H, now):
    # a sleek arc sweeps around a ring -- "processing / computing"
    cx, cy, rad = W // 2, H - 11, 8
    a0 = int(now * 200) % 360
    d.arc([cx - rad, cy - rad, cx + rad, cy + rad], start=a0, end=a0 + 210, fill=1, width=2)


def _link_dots(d, W, H, now):
    # three dots pulse in sequence -- "connecting / establishing link"
    cy = H - 11
    for i in range(3):
        t = (math.sin(now * 4 - i * 1.1) + 1) / 2          # staggered 0..1 pulse
        s = 1.5 + 2.5 * t
        x = W / 2 - 10 + i * 10
        d.ellipse([x - s / 2, cy - s / 2, x + s / 2, cy + s / 2], fill=1)


# act name -> overlay painter (activities without one just move the gaze)
OVERLAYS = {"thinking": _think, "searching": _magnifier,
            "working": _hammer, "listening": _headphones,
            "processing": _arc_ring, "connecting": _link_dots}
