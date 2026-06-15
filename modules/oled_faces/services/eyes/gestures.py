"""GESTURES -- the moving layer: blinks/winks and one-shot motions.
Adding a motion = one line in GESTURES_FN."""
from __future__ import annotations

import math

from .primitives import smoothstep

_PI = math.pi

# blink timeline: name -> (eyes, duration, closes, anchor)
# anchor is where the lid shuts: 0.5 centred, 1.0 from the top, 0.0 from the bottom.
BLINKS = {
    "blink":        ({"left", "right"}, 0.20, 1, 0.5),
    "double_blink": ({"left", "right"}, 0.44, 2, 0.5),
    "wink":         ({"right"}, 0.6, 1, 0.5),
    "wink_left":    ({"left"}, 0.6, 1, 0.5),
    "wink_right":   ({"right"}, 0.6, 1, 0.5),
    "blink_down":   ({"left", "right"}, 0.22, 1, 1.0),  # lids fall from the top
    "blink_up":     ({"left", "right"}, 0.22, 1, 0.0),  # lids close from the bottom
}


def _look(dx, dy, bias=0.0):
    """A real glance: dart toward (dx, dy) and -- for sideways looks -- swell the near
    eye while the far one shrinks (the parallax of the head turning). Hold, then return."""
    def fn(p, e):
        if p < 0.22:        # quick dart out
            hold = p / 0.22
        elif p > 0.80:      # quick return
            hold = (1.0 - p) / 0.20
        else:               # hold the look
            hold = 1.0
        hold = smoothstep(hold)               # ease the ramps
        s = 1.0 - 0.12 * hold                 # mild foreshorten (parallax carries the turn)
        return dx * hold, dy * hold, 0.0, s, s, bias * hold
    return fn


# one-shot motion: name -> (duration, fn(ph, env) -> (dx, dy, conv, scale_w, scale_h))
# ph 0..1 is gesture progress; env = sin(ph*pi) fades the move in and out.
GESTURES_FN = {
    "smoke":      (3.8, lambda p, e: (0.0, 0.0, 0.0, 1.0, 1.0)),                              # slow drag -- the cigarette does the work
    "nod":        (1.4, lambda p, e: (0.0, math.sin(p * _PI * 8) * 6 * e, 0.0, 1.0, 1.0)),    # two nods, same speed
    "refuse":     (1.2, lambda p, e: (math.sin(p * _PI * 12) * 9 * e, 0.0, 0.0, 1.0, 1.0)),   # two shakes, same speed
    "laugh":      (1.4, lambda p, e: (0.0, -abs(math.sin(p * _PI * 4)) * 7 * e, 0.0, 1.0, 1.0 - 0.4 * e)),
    "excited":    (0.9, lambda p, e: (0.0, -abs(math.sin(p * _PI * 5)) * 8 * e, 0.0, 1.0 + 0.22 * e, 1.0 + 0.22 * e)),
    "roll":       (0.9, lambda p, e: (math.cos(p * _PI * 2) * 11 * e, math.sin(p * _PI * 2) * 7 * e, 0.0, 1.0, 1.0)),
    "shiver":     (0.7, lambda p, e: (math.sin(p * _PI * 16) * 3 * e, math.cos(p * _PI * 22) * 2 * e, 0.0, 1.0, 1.0)),
    "cross_eyes": (0.9, lambda p, e: (0.0, 0.0, 9.0 * e, 1.0, 1.0)),
    "pop":        (0.5, lambda p, e: (0.0, 0.0, 0.0, 1.0 + 0.35 * e, 1.0 + 0.35 * e)),
    "squint":     (1.3, lambda p, e: (0.0, 0.0, 0.0, 1.0, 1.0 - 0.6 * e)),
    "scan":       (1.3, lambda p, e: (math.sin(p * _PI * 2) * 16 * e, 0.0, 0.0, 1.0, 1.0)),
    "look_left":  (1.2, _look(-8, 0, -0.2)),   # near (left) eye bigger, right smaller
    "look_right": (1.2, _look(8, 0, 0.2)),     # near (right) eye bigger, left smaller
    "look_up":    (1.2, _look(0, -10)),
    "look_down":  (1.2, _look(0, 10)),
    "acknowledge": (0.45, lambda p, e: (0.0, e * 8, 0.0, 1.0, 1.0)),                       # one crisp dip -- "on it"
    "scan_sweep":  (1.6, lambda p, e: (-math.sin(p * _PI * 2) * 15, 0.0, 0.0, 1.0, 1.0)),  # one smooth sensor sweep
}

def _smoking_act(d, W, H, p, e):
    """Lift the cigarette to the lips with a thin curl of smoke (like the smoking mood);
    on the slow inhale the wisp fades; on the exhale the cig pulls away and a thick plume pours out."""
    mx, my = W * 0.5, H - 9                            # the mouth
    lift = smoothstep(p / 0.12)                       # bring the cigarette up to the lips
    away = smoothstep((p - 0.55) / 0.30) if p > 0.55 else 0.0   # then pull it away on the exhale
    ax, ay = away * 10, away * 8
    rfx, rfy = W * 0.55, H - 1                          # resting hold, low
    # filter end at the lips; the body + ember reach out so the cigarette stays visible
    fx, fy = rfx + (mx - 4 - rfx) * lift + ax, rfy + (my - rfy) * lift + ay
    ex, ey = rfx + 18 + (mx + 16 - (rfx + 18)) * lift + ax, rfy - 3 + (my - 2 - (rfy - 3)) * lift + ay
    d.line([fx, fy, ex, ey], fill=1, width=3)         # cigarette body
    glow = 3 if 0.35 <= p < 0.55 else 2               # ember flares as the breath is drawn in
    d.ellipse([ex - glow, ey - glow, ex + glow, ey + glow], fill=1)

    thin = lift if p < 0.35 else max(0.0, 1.0 - smoothstep((p - 0.35) / 0.20))  # wisp fades on the inhale
    if thin > 0.03:
        pts = [(ex + math.sin(f * 4.5 - p * 9) * (f * f * 5), ey - 2 - f * 20 * thin)
               for f in (i / 10 for i in range(11))]
        d.line(pts, fill=1, width=1)                   # a single thin curl off the tip

    if p <= 0.55:
        return
    eq = (p - 0.55) / 0.45                            # 0..1 across the exhale
    rise = smoothstep(eq) * 1.7                       # the plume drifts slowly upward
    fade = 1.0 if eq < 0.4 else smoothstep((1.0 - eq) / 0.6)   # then dissipates gently, over a long tail
    for i in range(22):
        f = i / 21.0
        front = rise - f * 0.9
        if front <= 0:
            continue
        cxl = mx + math.sin(f * 3.4 + p * 4) * (2 + f * 11)
        spread = 3 + f * 16
        base = (2.5 + f * 8) * min(1.0, front * 2.4) * fade   # fade shrinks every puff toward the end
        for j in (-1, 0, 1):                          # a few puffs across the width -> a full, soft plume
            bx, by = cxl + j * spread * 0.5, my - f * (my + 2) - rise * 3   # the whole plume drifts up as it fades
            rad = base * (1.0 - 0.28 * abs(j))
            if rad > 0.5:
                d.ellipse([bx - rad, by - rad, bx + rad, by + rad], fill=1)


# gesture-time painters: name -> fn(d, W, H, ph, env), drawn on top of the face
GESTURE_FX = {"smoke": _smoking_act}

# while a gesture plays, wear another mood's eye-look (name -> mood whose paint to borrow)
GESTURE_FACE = {"smoke": "bored"}

GESTURES = ("none",) + tuple(BLINKS) + tuple(GESTURES_FN)
