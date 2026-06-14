"""MOODS -- static expressions. A mood is a size delta plus an optional painter
that carves lids onto a plain rounded-rect eye, plus optional decor around the
face. Most painters compose three lid shapes (_brow / _glare / _lids); the rest
are one-offs. Adding an emoji = one line in MOODS."""
from __future__ import annotations

import math

from .primitives import heart, sparkle


# ---- shared lid shapes carved (fill=0) onto an eye drawn as a rounded rect ------
def _brow(d, x, y, w, h, inner, outer, is_right):
    """Slanted top lid: covers to inner*h toward the nose, outer*h on the outside."""
    rt = y + h * (outer if is_right else inner)
    lt = y + h * (inner if is_right else outer)
    d.polygon([(x - 2, y - 2), (x + w + 2, y - 2), (x + w + 2, rt), (x - 2, lt)], fill=0)


def _glare(d, x, y, w, h, depth, is_right):
    """Inner-down brow: a triangle whose tip drops to depth*h toward the nose."""
    tip = (x - 2, y + h * depth) if is_right else (x + w + 2, y + h * depth)
    d.polygon([(x - 2, y - 2), (x + w + 2, y - 2), tip], fill=0)


def _lids(d, x, y, w, h, top=0.0, bottom=1.0):
    """Flat lids: cover down to top*h and up from bottom*h."""
    if top:
        d.rectangle([x - 1, y - 1, x + w + 1, y + h * top], fill=0)
    if bottom < 1:
        d.rectangle([x - 1, y + h * bottom, x + w + 1, y + h + 1], fill=0)


# ---- painters: signature (d, x, y, w, h, r, is_right). Static -- no motion. -----
def _happy(d, x, y, w, h, r, ir):  # cheeks-up smile: arc carved into the bottom
    d.ellipse([x - w * 0.25, y + h * 0.45, x + w * 1.25, y + h * 2.1], fill=0)


def _sad(d, x, y, w, h, r, ir):       _brow(d, x, y, w, h, 0.30, 0.66, ir)  # downcast droop
def _tired(d, x, y, w, h, r, ir):     _brow(d, x, y, w, h, 0.38, 0.52, ir)  # hooded, peering out
def _worried(d, x, y, w, h, r, ir):   _brow(d, x, y, w, h, 0.02, 0.26, ir)  # raised inner brow
def _angry(d, x, y, w, h, r, ir):     _glare(d, x, y, w, h, 0.60, ir)       # glare
def _furious(d, x, y, w, h, r, ir):   _glare(d, x, y, w, h, 0.78, ir)       # rage (angry++)
def _bored(d, x, y, w, h, r, ir):     _lids(d, x, y, w, h, top=0.5)         # flat half-lids
def _focused(d, x, y, w, h, r, ir):   _lids(d, x, y, w, h, 0.24, 0.76)      # determined band
def _sleepy(d, x, y, w, h, r, ir):    _lids(d, x, y, w, h, 0.5, 0.82)       # droopy slits
def _despair(d, x, y, w, h, r, ir):   _lids(d, x, y, w, h, 0.42, 0.62)      # drained slit
def _attentive(d, x, y, w, h, r, ir): _lids(d, x, y, w, h, top=0.12)        # crisp top lid -- locked on
def _standby(d, x, y, w, h, r, ir):   _lids(d, x, y, w, h, 0.34, 0.70)      # calm low-power band
def _smoking(d, x, y, w, h, r, ir):   _lids(d, x, y, w, h, top=0.45)        # heavy-lidded, chilled out


def _skeptical(d, x, y, w, h, r, ir):  # one eye narrowed+angled, the other barely lidded
    if ir:
        _lids(d, x, y, w, h, top=0.14)
    else:
        d.polygon([(x - 2, y - 2), (x + w + 2, y - 2),
                   (x + w + 2, y + h * 0.5), (x - 2, y + h * 0.66)], fill=0)


def _confused(d, x, y, w, h, r, ir):  # only the lower (right) eye squints
    if ir:
        _lids(d, x, y, w, h, top=0.28)


def _dumb(d, x, y, w, h, r, ir):  # punch a glint out of each eye
    g = max(2.0, w * 0.2)
    d.ellipse([x + w * 0.22, y + h * 0.2, x + w * 0.22 + g, y + h * 0.2 + g], fill=0)


def _dead(d, x, y, w, h, r, ir):  # KO -- an X carved across the eye
    lw = max(2, int(w * 0.16))
    d.line([x + 3, y + 3, x + w - 4, y + h - 4], fill=0, width=lw)
    d.line([x + w - 4, y + 3, x + 3, y + h - 4], fill=0, width=lw)


def _decor_lovely(d, W, H, now, ox=0.0, oy=0.0):  # little hearts & sparkles scattered around -- smitten
    spots = ((0.50, 0.07), (0.24, 0.14), (0.76, 0.12), (0.05, 0.40), (0.95, 0.42),
             (0.07, 0.74), (0.93, 0.72), (0.28, 0.90), (0.72, 0.88))
    for i, (fx, fy) in enumerate(spots):
        (heart if i % 2 == 0 else sparkle)(d, fx * W, fy * H, 9 if i % 2 == 0 else 4)


def _decor_smoke(d, W, H, now, ox=0.0, oy=0.0):  # a lit cigarette, slightly right; smoke off the tip
    dx, dy = ox, oy                                   # locked to the face -- fixed eye-to-mouth gap (off-screen on big looks is fine)
    hx, hy = W * 0.58 + dx, H - 10 + dy               # holder (fingers) end, with clearance below the eye
    tx, ty = W * 0.74 + dx, H - 7 + dy                # burning tip, angled only slightly down
    d.line([hx, hy, tx, ty], fill=1, width=4)        # cigarette body -- short, thick stick
    d.ellipse([tx - 2, ty - 2, tx + 2, ty + 2], fill=1)  # glowing ember tip
    # smoke: straight at the source (laminar), slowly widening into a single curl higher up
    pts = [(tx + math.sin(f * 4.5 - now * 0.9) * (f * f * 8), ty - 2 - f * (ty - 4))
           for f in (i / 15 for i in range(16))]     # <1 wavelength -> one bend, not two lines
    d.line(pts, fill=1, width=2, joint="curve")      # a single slow, flowing smoke line


# spec keys: dw/dh size delta, tilt per-eye y offset, bias per-eye size skew,
# paint lid carver, decor face extras. Everything is optional.
MOODS = {
    "neutral":     {},
    "happy":       {"paint": _happy},
    "sad":         {"dw": -4, "dh": -6, "paint": _sad},   # small + downcast
    "angry":       {"paint": _angry},
    "tired":       {"paint": _tired},
    "sleepy":      {"dh": -20, "paint": _sleepy},
    "surprised":   {"dw": -4, "dh": 10},
    "lovely":      {"dw": 2, "dh": 2, "decor": _decor_lovely},
    "skeptical":   {"paint": _skeptical},
    "focused":     {"paint": _focused},
    "dumb":        {"dw": 4, "dh": 4, "paint": _dumb},
    "confused":    {"tilt": 4, "paint": _confused},
    "bored":       {"paint": _bored},
    "scared":      {"dw": -10, "dh": -4},
    "dead":        {"paint": _dead},
    "alert":       {"dw": -18},                            # two upright bars
    "furious":     {"dw": 2, "dh": 2, "paint": _furious},
    "worried":     {"dh": 2, "paint": _worried},           # open eyes + concerned brow
    "despair":     {"dw": -8, "dh": -6, "paint": _despair},
    "disoriented": {"tilt": 4, "bias": 0.3},               # mismatched sizes + tilt -- woozy
    "attentive":   {"dw": 2, "dh": 2, "paint": _attentive},  # leaned in, locked on -- "go ahead"
    "standby":     {"dw": -6, "dh": -6, "paint": _standby},  # dim low-power idle -- ready, not off
    "smoking":     {"dh": -4, "paint": _smoking, "decor": _decor_smoke},  # chilled, thin smoke curling up
}
EMOTIONS = tuple(MOODS)
