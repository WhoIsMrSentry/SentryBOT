from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time


@dataclass
class Rule:
    id: str
    priority: str = "medium"  # critical|high|medium|low
    when: Dict[str, Any] = field(default_factory=dict)
    action: Dict[str, Any] = field(default_factory=dict)
    cooldown_ms: int = 0
    _last_ts: float = field(default=0.0, init=False, repr=False)

    def ready(self) -> bool:
        if self.cooldown_ms <= 0:
            return True
        return (time.time() - self._last_ts) * 1000.0 >= self.cooldown_ms

    def stamp(self) -> None:
        self._last_ts = time.time()


def priority_rank(p: str) -> int:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "idle": 0}
    return order.get(p.lower(), 0)


def eval_condition(cond: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    # Supported keys
    def get(name: str):
        return ctx.get(name)

    # Events
    if "event" in cond:
        ev = get("event")
        return ev == cond["event"]

    # Simple comparisons
    def ge(a, b): return (a is not None and b is not None and a >= b)
    def lt(a, b): return (a is not None and b is not None and a < b)

    m = get("metrics") or {}

    if "cpu_temp_gte" in cond and not ge(m.get("cpu_temp"), cond["cpu_temp_gte"]):
        return False
    if "cpu_temp_lt" in cond and not lt(m.get("cpu_temp"), cond["cpu_temp_lt"]):
        return False
    if "cpu_load_gte" in cond and not ge(m.get("cpu_load"), cond["cpu_load_gte"]):
        return False
    if "net_burst" in cond:
        # expect ctx["net_burst"] boolean set by engine heuristic
        if bool(cond["net_burst"]) != bool(get("net_burst")):
            return False
    if "arduino_connected" in cond:
        ac = get("arduino_connected")
        if ac is None or bool(cond["arduino_connected"]) != bool(ac):
            return False
    return True
