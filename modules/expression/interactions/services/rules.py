from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("interactions.rules")

SUPPORTED_CONDITION_KEYS = frozenset({
    "event",
    "cpu_temp_gte",
    "cpu_temp_lt",
    "cpu_load_gte",
    "net_burst",
    "arduino_connected",
    "quiet_hours_active",
})
SUPPORTED_RULE_KEYS = frozenset({"id", "priority", "when", "action", "cooldown_ms", "enabled"})
SUPPORTED_ACTION_KEYS = frozenset({"effect", "base", "companion"})
SUPPORTED_PRIORITIES = frozenset({"critical", "high", "medium", "low", "idle"})


@dataclass
class Rule:
    id: str
    priority: str = "medium"  # critical|high|medium|low|idle
    when: Dict[str, Any] = field(default_factory=dict)
    action: Dict[str, Any] = field(default_factory=dict)
    cooldown_ms: int = 0
    _last_ts: float = field(default=0.0, init=False, repr=False)
    _last_mono: Optional[float] = field(default=None, init=False, repr=False)
    _last_matched_ts: Optional[float] = field(default=None, init=False, repr=False)
    _trigger_count: int = field(default=0, init=False, repr=False)

    def cooldown_remaining_ms(self, now_mono: Optional[float] = None) -> int:
        if self.cooldown_ms <= 0 or self._last_mono is None:
            return 0
        now_m = time.monotonic() if now_mono is None else now_mono
        elapsed_ms = max(0.0, (now_m - self._last_mono) * 1000.0)
        rem = float(self.cooldown_ms) - elapsed_ms
        return int(rem + 0.999) if rem > 0.0 else 0

    def ready(self) -> bool:
        return self.cooldown_remaining_ms() <= 0

    def mark_matched(self) -> None:
        self._last_matched_ts = time.time()

    def stamp(self) -> None:
        now_wall = time.time()
        self._last_ts = now_wall
        self._last_mono = time.monotonic()
        self._last_matched_ts = now_wall
        self._trigger_count += 1

    def trace_snapshot(self, now_mono: Optional[float] = None) -> Dict[str, Any]:
        rem = self.cooldown_remaining_ms(now_mono=now_mono)
        return {
            "id": self.id,
            "priority": self.priority,
            "when": dict(self.when),
            "action": dict(self.action),
            "cooldown_ms": int(self.cooldown_ms),
            "ready": rem <= 0,
            "cooldown_remaining_ms": rem,
            "last_triggered_at": self._last_ts if self._trigger_count > 0 else None,
            "last_matched_at": self._last_matched_ts,
            "trigger_count": self._trigger_count,
        }


def priority_rank(p: str) -> int:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "idle": 0}
    return order.get(str(p or "").lower(), 0)


def validate_rules_config(raw_rules: Any) -> List[str]:
    """Validate configured rules and return human-readable warnings."""
    warnings: List[str] = []
    if not isinstance(raw_rules, list):
        return ["rules must be a list"]
    seen_ids: set[str] = set()
    for idx, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            warnings.append(f"rules[{idx}] is not a mapping")
            continue
        rid = str(item.get("id") or f"rules[{idx}]").strip()
        if not str(item.get("id") or "").strip():
            warnings.append(f"rules[{idx}] is missing non-empty 'id'")
        elif rid in seen_ids:
            warnings.append(f"duplicate rule id '{rid}'")
        seen_ids.add(rid)

        unknown_rule = sorted(set(item.keys()) - SUPPORTED_RULE_KEYS)
        if unknown_rule:
            warnings.append(f"rule '{rid}' has unknown keys: {', '.join(unknown_rule)}")

        prio = str(item.get("priority", "medium")).lower()
        if prio not in SUPPORTED_PRIORITIES:
            warnings.append(f"rule '{rid}' has unknown priority '{item.get('priority')}'")

        when = item.get("when")
        if not isinstance(when, dict) or not when:
            warnings.append(f"rule '{rid}' has empty or invalid 'when' condition")
        else:
            unknown_when = sorted(set(when.keys()) - SUPPORTED_CONDITION_KEYS)
            if unknown_when:
                warnings.append(
                    f"rule '{rid}' has unknown condition keys: {', '.join(unknown_when)}"
                )

        action = item.get("action")
        if not isinstance(action, dict) or not action:
            warnings.append(f"rule '{rid}' has empty or invalid 'action'")
        else:
            unknown_act = sorted(set(action.keys()) - SUPPORTED_ACTION_KEYS)
            if unknown_act:
                warnings.append(f"rule '{rid}' has unknown action keys: {', '.join(unknown_act)}")

        try:
            cd = int(item.get("cooldown_ms", 0))
            if cd < 0:
                warnings.append(f"rule '{rid}' has negative cooldown_ms={cd}")
        except (TypeError, ValueError):
            warnings.append(f"rule '{rid}' has invalid cooldown_ms={item.get('cooldown_ms')!r}")

    return warnings


def eval_condition(cond: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    """Evaluate a rule's `when` condition against current context (fail-closed on unknown keys)."""
    if not isinstance(cond, dict) or not cond:
        return False

    unknown = set(cond.keys()) - SUPPORTED_CONDITION_KEYS
    if unknown:
        logger.debug("Ignoring condition with unknown keys: %s", sorted(unknown))
        return False

    def get(name: str) -> Any:
        return ctx.get(name)

    if "event" in cond:
        if get("event") != cond["event"]:
            return False
        if len(cond) == 1:
            return True

    def ge(a: Any, b: Any) -> bool:
        return a is not None and b is not None and a >= b

    def lt(a: Any, b: Any) -> bool:
        return a is not None and b is not None and a < b

    m = get("metrics") or {}

    if "cpu_temp_gte" in cond and not ge(m.get("cpu_temp"), cond["cpu_temp_gte"]):
        return False
    if "cpu_temp_lt" in cond and not lt(m.get("cpu_temp"), cond["cpu_temp_lt"]):
        return False
    if "cpu_load_gte" in cond and not ge(m.get("cpu_load"), cond["cpu_load_gte"]):
        return False
    if "net_burst" in cond:
        if bool(cond["net_burst"]) != bool(get("net_burst")):
            return False
    if "arduino_connected" in cond:
        ac = get("arduino_connected")
        if ac is None or bool(cond["arduino_connected"]) != bool(ac):
            return False
    if "quiet_hours_active" in cond:
        qh = get("quiet_hours_active")
        if qh is None or bool(cond["quiet_hours_active"]) != bool(qh):
            return False
    return True
