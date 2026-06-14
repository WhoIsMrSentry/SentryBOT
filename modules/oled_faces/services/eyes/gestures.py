"""GESTURES -- the moving layer: blinks/winks and one-shot motions.
Adding a motion = one line in GESTURES_FN."""
from __future__ import annotations

import math

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
        hold = hold * hold * (3 - 2 * hold)   # smoothstep the ramps
        s = 1.0 - 0.12 * hold                 # mild foreshorten (parallax carries the turn)
        return dx * hold, dy * hold, 0.0, s, s, bias * hold
    return fn


# one-shot motion: name -> (duration, fn(ph, env) -> (dx, dy, conv, scale_w, scale_h))
# ph 0..1 is gesture progress; env = sin(ph*pi) fades the move in and out.
GESTURES_FN = {
    "nod":        (0.7, lambda p, e: (0.0, math.sin(p * _PI * 4) * 6 * e, 0.0, 1.0, 1.0)),
    "refuse":     (0.6, lambda p, e: (math.sin(p * _PI * 6) * 9 * e, 0.0, 0.0, 1.0, 1.0)),
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
    "boot_up":     (0.6, lambda p, e: (0.0, 0.0, 0.0, 0.15 + 0.85 * p, 0.15 + 0.85 * p)),  # iris in from nothing
    "power_down":  (0.7, lambda p, e: (0.0, 0.0, 0.0, 1.0 - 0.85 * e, 1.0 - 0.92 * e)),    # collapse to a dot -- sign-off
    "scan_sweep":  (1.6, lambda p, e: (-math.sin(p * _PI * 2) * 15, 0.0, 0.0, 1.0, 1.0)),  # one smooth sensor sweep
}

GESTURES = ("none",) + tuple(BLINKS) + tuple(GESTURES_FN)
