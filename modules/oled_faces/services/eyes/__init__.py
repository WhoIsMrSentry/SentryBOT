"""Procedural robot eyes for a 128x64 OLED, drawn with PIL.

Three strictly-separate layers, one module each:
  * moods.py      -- MOODS: a *static* expression (size + lid painter + decor).
  * gestures.py   -- GESTURES: the *moving* layer, a one-shot enveloped wobble.
  * activities.py -- ACTIVITIES: a looping tool-status (gaze pose + overlay icon).
engine.py wires them into the threaded eye renderer; primitives.py holds the
shared drawing helpers. Adding an emoji/motion/status = one line in its module.
"""
from .activities import ACTIVITIES
from .engine import EyeEngine
from .gestures import GESTURES
from .moods import EMOTIONS

__all__ = ["EyeEngine", "EMOTIONS", "GESTURES", "ACTIVITIES"]
