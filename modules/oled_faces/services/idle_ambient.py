"""Pick ambient Pip faces while the robot is otherwise idle."""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from .mapper import OledAction


class IdleAmbientPlayer:
    def __init__(self, cfg: Dict[str, Any]):
        block = dict(cfg.get("idle_ambient", {}) if isinstance(cfg.get("idle_ambient"), dict) else {})
        self.enabled = bool(block.get("enabled", True))
        self.min_interval_s = float(block.get("min_interval_s", 14.0))
        self.max_interval_s = float(block.get("max_interval_s", 42.0))
        self.hold_s = float(block.get("hold_s", 9.0))
        self.priority = int(block.get("priority", 32))
        self._pool: List[OledAction] = []
        for item in block.get("pool", []) or []:
            if not isinstance(item, dict):
                continue
            mode = str(item.get("mode", "bitmap")).strip().lower()
            name = str(item.get("name", "neutral")).strip().lower()
            if mode and name:
                self._pool.append(OledAction(mode=mode, name=name))
        if not self._pool:
            self._pool = [
                OledAction(mode="bitmap", name="smoking"),
                OledAction(mode="animation", name="thinking"),
                OledAction(mode="bitmap", name="bored"),
                OledAction(mode="animation", name="searching"),
                OledAction(mode="bitmap", name="lovely"),
                OledAction(mode="animation", name="working"),
                OledAction(mode="bitmap", name="skeptical"),
                OledAction(mode="gesture", name="nod"),
            ]
        self._next_at = 0.0
        self._hold_until = 0.0
        self._bag: List[OledAction] = []

    def maybe_action(self, *, blocked: bool) -> Optional[OledAction]:
        if not self.enabled or blocked:
            return None
        now = time.time()
        if now < self._hold_until:
            return None
        if now < self._next_at:
            return None
        action = self._draw()
        self._hold_until = now + max(1.0, self.hold_s)
        gap = random.uniform(self.min_interval_s, self.max_interval_s)
        self._next_at = self._hold_until + gap
        return action

    def _draw(self) -> OledAction:
        if not self._bag:
            self._bag = list(self._pool)
            random.shuffle(self._bag)
        return self._bag.pop()
