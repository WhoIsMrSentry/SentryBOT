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


def _suspicious(d, x, y, w, h, r, ir): _lids(d, x, y, w, h, 0.40, 0.88)      # heavy slit + pinched bottom -- side-eye


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


def _decor_coffee(d, W, H, now, ox=0.0, oy=0.0):  # a steaming mug, bottom-right -- "wired / caffeinated"
    cx, cy = W - 20, H - 11
    d.rounded_rectangle([cx, cy, cx + 12, cy + 9], radius=2, fill=1)              # cup body
    d.arc([cx + 11, cy + 1, cx + 17, cy + 8], start=-80, end=80, fill=1, width=2)  # handle
    for i in range(2):                                                            # two rising steam curls
        sx = cx + 3 + i * 6
        pts = [(sx + math.sin(f * 5 - now * 3) * 2.5, cy - 1 - f * 9) for f in (j / 6 for j in range(7))]
        d.line(pts, fill=1, width=1, joint="curve")


def _decor_sweat(d, W, H, now, ox=0.0, oy=0.0):  # a nervous bead wells up by the brow then slides -- "nervous"
    t = (now * 0.8) % 1.0
    x, y, s = W - 16 + int(ox), 8 + t * 11, 3
    d.ellipse([x - s * 0.7, y - s * 0.3, x + s * 0.7, y + s], fill=1)             # rounded body
    d.polygon([(x, y - s - 3), (x - s * 0.6, y - s * 0.2), (x + s * 0.6, y - s * 0.2)], fill=1)  # pointed top


def _decor_cloud(d, W, H, now, ox=0.0, oy=0.0):  # a little rain cloud drizzles overhead -- "gloomy"
    cx, cy = W // 2 + int(ox), 7
    for dx, r in ((-7, 4), (0, 5), (7, 4)):                                       # three lumps + flat base
        d.ellipse([cx + dx - r, cy - r, cx + dx + r, cy + r], fill=1)
    d.rectangle([cx - 11, cy, cx + 11, cy + 3], fill=1)
    for i in range(4):                                                            # falling rain streaks
        t = (now * 1.5 + i / 4) % 1.0
        rx, ry = cx - 9 + i * 6, cy + 5 + t * 12
        d.line([rx, ry, rx - 1, ry + 3], fill=1, width=1)


def _decor_vein(d, W, H, now, ox=0.0, oy=0.0):  # a cross-shaped popping anger vein throbs by the brow -- furious
    cx, cy = 16 + int(ox), 8
    s = 5 + (math.sin(now * 9) + 1)                                               # throb 5..7
    for a in (45, 135, 225, 315):                                                # four inward chevrons (the 💢 cross)
        ax, ay = math.cos(math.radians(a)), math.sin(math.radians(a))
        ex, ey = cx + ax * s, cy + ay * s
        d.line([ex, ey, ex - ax * 3 - ay * 2, ey - ay * 3 + ax * 2], fill=1, width=1)
        d.line([ex, ey, ex - ax * 3 + ay * 2, ey - ay * 3 - ax * 2], fill=1, width=1)


def _decor_sleep(d, W, H, now, ox=0.0, oy=0.0):  # "z z Z" drift up and grow -- sleepy
    for i in range(3):
        t = (now * 0.5 + i / 3) % 1.0
        x, y = W // 2 + 16 + i * 6 + int(ox), H // 2 - 2 - t * 22
        d.text((x, y), "Z" if i == 2 else "z", fill=1)


# pixel-art "deal-with-it" shades: connected top frame, two lenses stepping down-inward.
# '#' = dark lens block; gaps inside a lens are the white gleam ("one-way" glow).
_SHADES_ART = (
    "################################",   # connected top bar
    "###############  ###############",   # center bridge notch
    " ## # ########    ## # ######## ",   # gleam streaks, lower-left of each lens
    "  ## # #######     ## # ######  ",
    "   ## # #####       ## # ####   ",
    "    ########         #######    ",   # angled lens bottoms
)
_SHADES_BLOCKS = [(c, r) for r, row in enumerate(_SHADES_ART)  # block (col, row) coords, scanned once
                  for c, ch in enumerate(row) if ch == "#"]


def _decor_cool(d, W, H, now, ox=0.0, oy=0.0):  # pixel-art shades, no eyes -- wanders side to side like eyes
    u = 3                                                      # pixel-block size (96x48 -> leaves room to wander)
    sway = round(math.sin(now * 0.7) * 9 + math.sin(now * 1.7) * 4)   # organic side-to-side wander
    x0 = (W - len(_SHADES_ART[0]) * u) // 2 + sway
    y0 = (H - len(_SHADES_ART) * u) // 2 + round(math.sin(now * 0.9) * 2)  # a small vertical bob
    for c, r in _SHADES_BLOCKS:
        px, py = x0 + c * u, y0 + r * u
        d.rectangle([px, py, px + u - 1, py + u - 1], fill=1)


def _decor_devil(d, W, H, now, ox=0.0, oy=0.0):  # two sharply-angled horns + a clean swaying tail -- "devil"
    d.polygon([(30, 21), (41, 18), (18, 2)], fill=1)          # left horn, angled up-left
    d.polygon([(W - 30, 21), (W - 41, 18), (W - 18, 2)], fill=1)  # right horn, angled up-right
    bx, by = W - 6, H - 1                                      # tail from the bottom-right corner
    tx, ty = W - 13 + math.sin(now * 2.2) * 3, H - 23          # tip sways gently
    d.line([(bx, by), (W - 16, H - 12), (tx, ty)], fill=1, width=2, joint="curve")
    d.polygon([(tx - 3, ty + 2), (tx + 3, ty + 2), (tx, ty - 5)], fill=1)  # spade barb


def _decor_kawaii(d, W, H, now, ox=0.0, oy=0.0):  # rosy blush hatch + twinkles -- "kawaii"
    for cx in (14, W - 24):                                    # a blush patch under each eye -- tracks the gaze
        for i in range(3):
            d.line([cx + i * 4 + ox, H - 12 + oy, cx + 3 + i * 4 + ox, H - 7 + oy], fill=1, width=1)
    for fx, fy, s in ((0.07, 0.16, 4), (0.93, 0.18, 4), (0.5, 0.06, 3)):
        sparkle(d, fx * W, fy * H, s)                          # ambient twinkles stay put


# spec keys: dw/dh size delta, tilt per-eye y offset, bias per-eye size skew, paint lid
# carver, decor face extras, bright panel brightness 0..255, bare draw no eyes. All optional.
MOODS = {
    "neutral":     {},
    "smoking":     {"dh": -4, "paint": _smoking, "decor": _decor_smoke},  # chilled, thin smoke curling up
    "happy":       {"paint": _happy},
    "sad":         {"dw": -4, "dh": -6, "paint": _sad},   # small + downcast
    "angry":       {"paint": _angry},
    "tired":       {"paint": _tired},
    "sleepy":      {"dh": -20, "paint": _sleepy, "decor": _decor_sleep},  # droopy slits + drifting Zzz
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
    "furious":     {"dw": 2, "dh": 2, "paint": _furious, "decor": _decor_vein},  # rage + popping vein
    "worried":     {"dh": 2, "paint": _worried},           # open eyes + concerned brow
    "despair":     {"dw": -8, "dh": -6, "paint": _despair},
    "disoriented": {"tilt": 4, "bias": 0.3},               # mismatched sizes + tilt -- woozy
    "attentive":   {"dw": 2, "dh": 2, "paint": _attentive},  # leaned in, locked on -- "go ahead"
    "standby":     {"dw": -2, "dh": -24, "bright": 1},      # low dashes + dimmed panel -- low-power sleep
    "suspicious":  {"dw": -2, "paint": _suspicious},                      # narrow slit eyes -- side-eye
    "awe":         {"dw": 4, "dh": 14},                                   # huge open eyes -- pure wonder
    "wired":       {"dw": 2, "dh": 2, "decor": _decor_coffee},            # caffeinated -- steaming mug
    "nervous":     {"dw": -2, "paint": _worried, "decor": _decor_sweat},  # anxious brow + sweat bead
    "gloomy":      {"dw": -2, "dh": -4, "paint": _sad, "decor": _decor_cloud},  # downcast + little rain cloud
    "cool":        {"bare": True, "decor": _decor_cool},                  # just the aviators -- no eyes drawn
    "devil":       {"paint": _angry, "decor": _decor_devil},              # evil glare + horns & tail
    "kawaii":      {"dw": 2, "dh": 0, "decor": _decor_kawaii},            # round eyes + blush below + twinkles
}
EMOTIONS = tuple(MOODS)
