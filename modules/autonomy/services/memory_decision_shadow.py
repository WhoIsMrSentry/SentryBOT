from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return " ".join(text.split())


def _lower_tokens(*values: Any) -> str:
    parts: List[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(x) for x in value)
        elif isinstance(value, dict):
            parts.extend(str(k) for k in value.keys())
            parts.extend(str(v) for v in value.values())
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MemoryDecisionShadow:
    """Read-only memory influence evaluator.

    Recency guard is intentionally here, before needs bias. A remembered hazard,
    object, or sound can suggest behavior only while it is fresh enough. This
    prevents persistent world_memory.json entries from locking the robot into a
    stale safety/exploration state after restarts.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "mode": "shadow",
        "max_items": 25,
        "fresh_window_s": 180.0,
        "max_age_s": 240.0,
        "safety_max_age_s": 45.0,
        "social_max_age_s": 180.0,
        "exploration_max_age_s": 240.0,
        "curiosity_max_age_s": 180.0,
        "balance_max_age_s": 600.0,
        "unknown_age_score": 0.35,
        "apply_to_needs": False,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    def evaluate(self, memory_snapshot: Optional[Dict[str, Any]] = None, recent: Optional[List[Dict[str, Any]]] = None, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        if not self.enabled():
            return {"ok": True, "enabled": False, "mode": "shadow", "available": False, "reason": "disabled", "apply_to_needs": False, "timestamp": ts, "influences": [], "stale_count": 0}
        snapshot = _as_dict(memory_snapshot)
        if recent is None:
            recent = _as_list(snapshot.get("recent"))
        items = [x for x in recent if isinstance(x, dict)]
        max_items = int(_num(self.cfg.get("max_items"), 25))
        if max_items > 0:
            items = items[:max_items]
        influences: List[Dict[str, Any]] = []
        stale: List[Dict[str, Any]] = []
        for item in items:
            influence, stale_marker = self._influence_or_stale_for_item(item, ts)
            if influence:
                influences.append(influence)
            elif stale_marker:
                stale.append(stale_marker)
        influences.sort(key=lambda x: (_num(x.get("score")), _num(x.get("confidence"))), reverse=True)
        top = influences[0] if influences else {}
        return {
            "ok": True,
            "enabled": True,
            "mode": str(self.cfg.get("mode") or "shadow"),
            "apply_to_needs": bool(self.cfg.get("apply_to_needs", False)),
            "available": bool(influences),
            "reason": "memory_shadow_hint" if influences else ("memory_hints_stale" if stale else "no_memory_hint"),
            "timestamp": ts,
            "total_memory": int(_num(snapshot.get("total"), len(items))),
            "considered": len(items),
            "stale_count": len(stale),
            "stale": stale[:10],
            "influences": influences[:10],
            "recommended_need": top.get("need", ""),
            "recommended_goal": top.get("goal", ""),
            "behavior": top.get("behavior", ""),
            "priority": top.get("priority", ""),
            "confidence": top.get("confidence", 0.0),
            "top_source": top.get("source", ""),
            "top_item": top.get("item", {}),
        }

    def _item_age(self, item: Dict[str, Any], now: float) -> float:
        last_seen = _num(item.get("last_seen_ts"), 0.0)
        if last_seen <= 0.0:
            return -1.0
        return max(0.0, now - last_seen)

    def _age_score(self, item: Dict[str, Any], now: float) -> float:
        last_seen = _num(item.get("last_seen_ts"), 0.0)
        if last_seen <= 0.0:
            return max(0.0, min(1.0, _num(self.cfg.get("unknown_age_score"), 0.35)))
        age = max(0.0, now - last_seen)
        window = max(1.0, _num(self.cfg.get("fresh_window_s"), 180.0))
        return max(0.0, 1.0 - min(age / window, 1.0))

    def _age_limit_for_need(self, need: str) -> float:
        if need == "safety":
            return max(1.0, _num(self.cfg.get("safety_max_age_s"), 45.0))
        if need == "social":
            return max(1.0, _num(self.cfg.get("social_max_age_s"), 180.0))
        if need == "exploration":
            return max(1.0, _num(self.cfg.get("exploration_max_age_s"), 240.0))
        if need == "curiosity":
            return max(1.0, _num(self.cfg.get("curiosity_max_age_s"), 180.0))
        if need == "balance":
            return max(1.0, _num(self.cfg.get("balance_max_age_s"), 600.0))
        return max(1.0, _num(self.cfg.get("max_age_s"), 240.0))

    def _stale_marker(self, item: Dict[str, Any], need: str, age_s: float, limit_s: float, reason: str) -> Dict[str, Any]:
        return {
            "need": need,
            "reason": reason,
            "age_s": round(age_s, 1),
            "max_age_s": round(limit_s, 1),
            "source": _clean(item.get("source"), "memory"),
            "item": {"id": item.get("id"), "kind": item.get("kind"), "name": item.get("name"), "summary": item.get("summary")},
        }

    def _mk(self, item: Dict[str, Any], need: str, goal: str, behavior: str, priority: str, base: float, reason: str, now: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        age_s = self._item_age(item, now)
        limit_s = self._age_limit_for_need(need)
        if age_s >= 0.0 and age_s > limit_s:
            return {}, self._stale_marker(item, need, age_s, limit_s, f"{reason}.stale")
        conf = max(0.0, min(1.0, _num(item.get("confidence"), 0.6)))
        salience = max(0.0, min(1.0, _num(item.get("salience"), conf)))
        age_score = self._age_score(item, now)
        score = max(0.0, min(1.0, base * 0.45 + conf * 0.25 + salience * 0.20 + age_score * 0.10))
        return {
            "need": need,
            "goal": goal,
            "behavior": behavior,
            "priority": priority,
            "score": round(score, 4),
            "confidence": round(max(conf, score), 4),
            "reason": reason,
            "age_s": round(age_s, 1) if age_s >= 0.0 else None,
            "max_age_s": round(limit_s, 1),
            "source": _clean(item.get("source"), "memory"),
            "item": {"id": item.get("id"), "kind": item.get("kind"), "name": item.get("name"), "summary": item.get("summary")},
        }, {}

    def _influence_or_stale_for_item(self, item: Dict[str, Any], now: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        kind = _clean(item.get("kind")).lower()
        name = _clean(item.get("name"))
        summary = _clean(item.get("summary"))
        tokens = _lower_tokens(kind, name, summary, item.get("tags"), item.get("properties"), item.get("source"))
        if any(t in tokens for t in ["hazard", "loud", "obstacle", "safety", "danger"]):
            return self._mk(item, "safety", "pause_and_observe", "pause_and_observe", "critical", 0.96, "memory.safety", now)
        if any(t in tokens for t in ["wakeword", "speech", "owner", "person", "heard", "seen"]):
            return self._mk(item, "social", "seek_owner_or_invite_interaction", "engage_owner", "normal", 0.82, "memory.social", now)
        if kind == "objects" or any(t in tokens for t in ["novel", "unknown object", "new object"]):
            return self._mk(item, "exploration", "look_around_and_learn", "look_around_and_learn", "normal", 0.78, "memory.exploration", now)
        if any(t in tokens for t in ["sound", "noise", "curiosity"]):
            return self._mk(item, "curiosity", "inspect_environment", "inspect_environment", "normal", 0.74, "memory.curiosity", now)
        if any(t in tokens for t in ["quiet", "stable", "silence", "calm"]):
            return self._mk(item, "balance", "calm_idle", "calm_idle", "low", 0.58, "memory.balance", now)
        return {}, {}

    # Compatibility for tests/tools that used the old private helper name.
    def _influence_for_item(self, item: Dict[str, Any], now: float) -> Dict[str, Any]:
        influence, _stale = self._influence_or_stale_for_item(item, now)
        return influence
