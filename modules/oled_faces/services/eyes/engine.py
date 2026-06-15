"""EyeEngine -- threaded renderer wiring the three layers (mood / gesture / activity).

The moving layer holds ONE move at a time: a blink or a gesture. A commanded
gesture preempts it; the automatic blink and the mood-change mask-blink only fire
when it is free, so moves never overlap. A mood change that arrives while it is
busy waits in `_pending` and applies (masked) the moment it frees. A separate
eased pose (gaze + size) glides toward its target, so everything settles, never snaps.
"""
from __future__ import annotations

import math
import random
import threading
import time

from PIL import Image, ImageDraw

from .activities import ACT_MOOD, ACTIVITIES, OVERLAYS, pose
from .gestures import BLINKS, GESTURE_FACE, GESTURE_FX, GESTURES_FN
from .moods import MOODS
from .primitives import ease, rounded_rect

_TAU_GAZE, _TAU_SIZE = 0.09, 0.11            # gaze / eye-size settle time-constants
_AUTO = ({"left", "right"}, 0.20, 1, 0.5)    # spontaneous blink (eyes, dur, reps, anchor)
_MASK = ({"left", "right"}, 0.24, 1, 0.5)    # blink that hides a mood's lid swap


class EyeEngine:
    def __init__(self, show, *, width=128, height=64, fps=30,
                 eye_w=36, eye_h=36, radius=12, gap=10,
                 set_brightness=None, bright=255):        # bright = general panel brightness, max by default
        self._show = show
        self._set_brightness, self._bright = set_brightness, bright
        self._cur_bright = None                          # unset -> first frame pushes the general level
        self.W, self.H, self.fps = width, height, max(5, fps)
        self.eye_w, self.eye_h, self.radius, self.gap = eye_w, eye_h, radius, gap
        self.base_lx = (width - (2 * eye_w + gap)) // 2
        self.base_ly = (height - eye_h) // 2
        self._img = Image.new("1", (width, height), 0)   # one reused frame buffer
        self._draw = ImageDraw.Draw(self._img)

        self.gx = self.gy = 0.0                          # eased pose (thread-only)
        self.ew, self.eh = float(eye_w), float(eye_h)

        self._lock = threading.Lock()                    # guards the fields below
        self.mood = "neutral"
        self._pending = None                             # mood waiting for the layer to free
        self.look_x = self.look_y = 0.0                  # resting gaze target
        self._blink = self._gesture = self._activity = None
        self._restore_mood = None                        # mood to return to after a face-swapping gesture
        self._next_blink = self._next_idle = 0.0
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------------ API
    def start(self):
        if not (self._thread and self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="eye-engine", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)

    def set_mood(self, mood):
        m = mood.lower() if mood and mood.lower() in MOODS else "neutral"
        with self._lock:
            self._restore_mood = None                    # an explicit mood change cancels a pending gesture-restore
            if m == self.mood:
                self._pending = None
            elif self._blink or self._gesture:           # busy -> apply (masked) once free
                self._pending = m
            else:
                self.mood = m
                self._begin_blink(time.monotonic(), _MASK)

    def play_gesture(self, name):
        """Play a commanded blink/gesture; it preempts whatever is on the moving
        layer, so a sent emote is never dropped or overwritten by a default."""
        name = (name or "none").lower()
        now = time.monotonic()
        with self._lock:
            if self._restore_mood is not None:           # a prior face-gesture is interrupted -> restore its mood first
                self.mood, self._restore_mood = self._restore_mood, None
            if name in BLINKS:
                self._begin_blink(now, BLINKS[name])
            elif name in GESTURES_FN:
                self._blink = None
                self._gesture = {"kind": name, "start": now, "dur": GESTURES_FN[name][0]}
                if name in GESTURE_FACE:                  # wear another mood for the gesture, restore it when done
                    self._restore_mood = self.mood
                    self.mood, self._pending = GESTURE_FACE[name], None

    def set_activity(self, name):
        """Loop a status animation (thinking/scanning/...); 'idle' stops it. Each busy
        activity also wears a fitting face (thinking -> focused, ...)."""
        name = (name or "idle").lower()
        act = name if name in ACTIVITIES and name != "idle" else None
        if act in ACT_MOOD:
            self.set_mood(ACT_MOOD[act])                 # takes the lock itself
        with self._lock:
            self._activity = act

    # -------------------------------------------------------------- internals
    def _begin_blink(self, now, spec):
        """Start a blink, clearing the moving layer (caller holds the lock)."""
        eyes, dur, reps, anchor = spec
        self._gesture = None
        self._blink = {"eyes": set(eyes), "start": now, "dur": dur, "reps": reps, "anchor": anchor}

    def _run(self):
        now = last = time.monotonic()
        self._next_blink = now + random.uniform(2, 6)
        self._next_idle = now + random.uniform(1.5, 5)
        frame = 1.0 / self.fps
        while not self._stop.is_set():
            now = time.monotonic()
            dt = min(0.1, now - last)                     # clamp so a stall can't teleport the eyes
            last = now
            self._step(now, dt)
            try:
                self._show(self._render(now))
            except Exception:
                pass                                     # transient BLE/I2C hiccup -- keep going
            time.sleep(max(0.0, frame - (time.monotonic() - now)))

    def _step(self, now, dt):
        """Retire finished moves, schedule automatic ones, ease the pose to target."""
        with self._lock:
            if self._blink and now - self._blink["start"] > self._blink["dur"]:
                self._blink = None
            if self._gesture and now - self._gesture["start"] > self._gesture["dur"]:
                self._gesture = None
                if self._restore_mood is not None:        # face-swapping gesture finished -> restore the original mood
                    self.mood, self._restore_mood = self._restore_mood, None
            free = not (self._blink or self._gesture)
            if free and self._pending:                       # masked deferred mood swap
                self.mood, self._pending = self._pending, None
                self._begin_blink(now, _MASK)
            elif free and now >= self._next_blink:           # spontaneous blink
                self._begin_blink(now, _AUTO)
                self._next_blink = now + random.uniform(2, 6)
            elif free and self._activity is None and now >= self._next_idle:  # idle glance
                self.look_x, self.look_y = (0.0, 0.0) if random.random() < 0.3 else \
                    (random.uniform(-16, 16), random.uniform(-7, 7))
                self._next_idle = now + random.uniform(1.5, 5)
            mood, act, look = self.mood, self._activity, (self.look_x, self.look_y)

        spec = MOODS[mood]
        target = min(spec.get("bright", self._bright), self._bright)  # emote may dim, capped at the general max
        if self._set_brightness and target != self._cur_bright:
            try:
                self._set_brightness(target)
                self._cur_bright = target
            except Exception:
                pass                                      # BLE hiccup -- retry next frame

        bw = self.eye_w + spec.get("dw", 0)
        bh = self.eye_h + spec.get("dh", 0)
        if act:
            tx, ty, hmult = pose(act, now)
            bh *= hmult
        else:
            tx, ty = look
        self.gx = ease(self.gx, tx, dt, _TAU_GAZE)
        self.gy = ease(self.gy, ty, dt, _TAU_GAZE)
        self.ew = ease(self.ew, bw, dt, _TAU_SIZE)
        self.eh = ease(self.eh, bh, dt, _TAU_SIZE)

    def _render(self, now):
        with self._lock:                                 # snapshot; the dicts are never mutated in place
            mood, act, b, g = self.mood, self._activity, self._blink, self._gesture

        # blink: per-eye openness 1 -> 0 -> 1 (reps times); anchor = where the lid shuts
        ol = or_ = 1.0
        anchor = 0.5
        if b:
            o = 1.0 - abs(math.sin(min(1.0, (now - b["start"]) / b["dur"]) * b["reps"] * math.pi))
            anchor = b["anchor"]
            ol = o if "left" in b["eyes"] else ol
            or_ = o if "right" in b["eyes"] else or_

        # gesture: one enveloped move (dx, dy, convergence, scale_w, scale_h[, size-bias])
        dx = dy = conv = 0.0
        msw = msh = 1.0
        gbias = 0.0
        gkind = gph = genv = None
        if g:
            ph = min(1.0, (now - g["start"]) / g["dur"])
            gkind, gph, genv = g["kind"], ph, math.sin(ph * math.pi)
            ret = GESTURES_FN[g["kind"]][1](ph, genv)
            dx, dy, conv, msw, msh = ret[:5]
            gbias = ret[5] if len(ret) > 5 else 0.0

        spec = MOODS[mood]
        paint, tilt = spec.get("paint"), spec.get("tilt", 0.0)
        bias = spec.get("bias", 0.0) + gbias             # + = right eye bigger, left smaller

        d = self._draw
        d.rectangle([0, 0, self.W - 1, self.H - 1], fill=0)   # clear the reused buffer
        slot = self.base_lx + self.gx + dx                    # left eye's slot origin
        eyes = () if spec.get("bare") else \
            ((slot, ol, False), (slot + self.eye_w + self.gap, or_, True))  # 'bare' draws no eyes
        for sx, openness, right in eyes:
            es = 1.0 + (bias if right else -bias)             # parallax: the near eye swells
            w = max(2.0, self.ew * msw * es)
            ho = max(2.0, self.eh * msh * es)                 # open height (before the blink)
            h = max(2.0, ho * openness)
            ex = sx + (self.eye_w - w) / 2 + (-conv if right else conv)
            ey = self.base_ly + self.gy + dy + (tilt if right else -tilt) \
                + (self.eye_h - ho) / 2 + (ho - h) * anchor   # centre, then shut lid to anchor
            r = min(w, h) * self.radius / self.eye_w
            rounded_rect(d, ex, ey, w, h, r, 1)
            if openness > 0.6 and paint:                      # lids drop out while (half-)blinked
                paint(d, ex, ey, w, h, r, right)
        if spec.get("decor"):
            spec["decor"](d, self.W, self.H, now, self.gx, self.gy)
        if act in OVERLAYS:
            OVERLAYS[act](d, self.W, self.H, now)
        if gkind in GESTURE_FX:                           # gesture-time extras (e.g. a smoke cloud)
            GESTURE_FX[gkind](d, self.W, self.H, gph, genv)
        return self._img
