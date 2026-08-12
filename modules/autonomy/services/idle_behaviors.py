from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class IdleAction:
    name: str
    weight: int = 1
    min_interval_s: float = 8.0
    emotion_hint: Optional[str] = None


class IdleBehaviorPlanner:
    """Weighted idle action planner with per-action cooldown."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._last_run: Dict[str, float] = {}
        self._rng = random.Random()
        self.actions = self._load_actions()

    def _load_actions(self) -> List[IdleAction]:
        default = [
            IdleAction(name="LOOK_AROUND", weight=5, min_interval_s=6),
            IdleAction(name="BLINK", weight=4, min_interval_s=5),
            IdleAction(name="STRETCH", weight=2, min_interval_s=15),
            IdleAction(name="MONOLOGUE", weight=1, min_interval_s=25, emotion_hint="neutral"),
            IdleAction(name="SIGH", weight=2, min_interval_s=14, emotion_hint="tired"),
        ]

        cfg = self.config.get("behaviors", {}).get("idle_tree", {})
        path = cfg.get("path")
        if not path:
            path = os.path.join(os.path.dirname(__file__), "..", "config", "idle_behaviors.yml")
        path = os.path.abspath(str(path))

        if yaml is None or not os.path.exists(path):
            return default

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return default

        raw_actions = data.get("actions") if isinstance(data, dict) else None
        if not isinstance(raw_actions, list) or not raw_actions:
            return default

        parsed: List[IdleAction] = []
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().upper()
            if not name:
                continue
            parsed.append(
                IdleAction(
                    name=name,
                    weight=max(1, int(item.get("weight", 1))),
                    min_interval_s=max(0.0, float(item.get("min_interval_s", 8))),
                    emotion_hint=str(item.get("emotion_hint")).strip() if item.get("emotion_hint") else None,
                )
            )
        return parsed or default

    def pick(self, now: Optional[float] = None) -> Optional[IdleAction]:
        # Old random idle actions disabled in favor of the LLM Behavior Planner.
        # The autonomy tick will now use the needs_engine -> companion_goal_selector -> behavior_planner
        # to generate dynamic JSON ActionSchemas.
        return None

    def stamp(self, action_name: str, now: Optional[float] = None) -> None:
        self._last_run[str(action_name).upper()] = now if now is not None else time.time()
