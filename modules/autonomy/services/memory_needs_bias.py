from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return " ".join(text.split())


def _clamp(value: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, _num(value, lo)))


GOAL_BY_NEED: Dict[str, Tuple[str, str, str]] = {
    "social": ("seek_owner_or_invite_interaction", "engage_owner", "normal"),
    "exploration": ("look_around_and_learn", "look_around_and_learn", "normal"),
    "curiosity": ("inspect_environment", "inspect_environment", "normal"),
    "boredom": ("choose_idle_activity", "choose_idle_activity", "normal"),
    "rest": ("rest_quietly", "rest_quietly", "low"),
    "safety": ("pause_and_observe", "pause_and_observe", "critical"),
    "balance": ("calm_idle", "calm_idle", "low"),
}


class MemoryNeedsBias:
    """Applies memory hints to needs snapshots in a guarded way.

    This is not an executor. It only annotates and gently adjusts semantic need
    scores. Hardware execution remains behind the existing goal/auto/behavior
    gates and PC dry-run profile.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "mode": "bias",
        "apply_to_needs": True,
        "min_confidence": 0.58,
        "max_boost": 18.0,
        "safety_override": True,
        "safety_score_cap": 45.0,
        "allow_critical": True,
        "annotate_only_for_balance": True,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self._last: Dict[str, Any] = {
            "ok": True,
            "enabled": bool(self.cfg.get("enabled", True)),
            "mode": str(self.cfg.get("mode") or "bias"),
            "available": False,
            "applied": False,
            "reason": "never_evaluated",
            "timestamp": 0.0,
        }

    def snapshot(self) -> Dict[str, Any]:
        out = dict(self._last)
        out["enabled"] = bool(self.cfg.get("enabled", True))
        out["apply_to_needs"] = bool(self.cfg.get("apply_to_needs", True))
        out["min_confidence"] = float(self.cfg.get("min_confidence", 0.58) or 0.58)
        out["max_boost"] = float(self.cfg.get("max_boost", 18.0) or 18.0)
        return out

    def apply(self, needs_snapshot: Optional[Dict[str, Any]], memory_shadow: Optional[Dict[str, Any]], now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        needs = dict(_as_dict(needs_snapshot))
        shadow = _as_dict(memory_shadow)
        base_reason = {
            "ok": True,
            "enabled": bool(self.cfg.get("enabled", True)),
            "mode": str(self.cfg.get("mode") or "bias"),
            "apply_to_needs": bool(self.cfg.get("apply_to_needs", True)),
            "timestamp": ts,
            "available": False,
            "applied": False,
        }
        if not needs:
            self._last = dict(base_reason, reason="missing_needs")
            return {"ok": False, "available": False, "reason": "missing_needs"}
        if not bool(self.cfg.get("enabled", True)):
            marker = dict(base_reason, reason="disabled")
            self._attach(needs, marker)
            self._last = marker
            return needs
        if not bool(self.cfg.get("apply_to_needs", True)):
            marker = dict(base_reason, reason="apply_disabled")
            self._attach(needs, marker)
            self._last = marker
            return needs
        if not shadow or not shadow.get("available"):
            marker = dict(base_reason, reason="no_memory_hint")
            self._attach(needs, marker)
            self._last = marker
            return needs
        rec_need = _clean(shadow.get("recommended_need")).lower()
        rec_goal = _clean(shadow.get("recommended_goal"))
        rec_priority = _clean(shadow.get("priority"), "normal").lower()
        confidence = max(0.0, min(1.0, _num(shadow.get("confidence"), 0.0)))
        min_conf = float(self.cfg.get("min_confidence", 0.58) or 0.58)
        if rec_need not in GOAL_BY_NEED:
            marker = dict(base_reason, reason="unsupported_memory_need", available=True, memory_need=rec_need, confidence=confidence)
            self._attach(needs, marker)
            self._last = marker
            return needs
        if confidence < min_conf:
            marker = dict(base_reason, reason="memory_confidence_low", available=True, memory_need=rec_need, confidence=round(confidence, 4))
            self._attach(needs, marker)
            self._last = marker
            return needs
        if rec_priority == "critical" and not bool(self.cfg.get("allow_critical", True)):
            marker = dict(base_reason, reason="critical_bias_disabled", available=True, memory_need=rec_need, confidence=round(confidence, 4))
            self._attach(needs, marker)
            self._last = marker
            return needs

        previous_need = _clean(needs.get("dominant_need"))
        previous_goal = _clean(needs.get("recommended_goal"))
        scores = dict(_as_dict(needs.get("scores")))
        before_scores = {k: _num(v) for k, v in scores.items()}
        max_boost = max(0.0, float(self.cfg.get("max_boost", 18.0) or 18.0))
        boost = round(max_boost * confidence, 2)
        applied = False
        reason = "memory_bias_applied"

        if rec_need == "safety":
            if bool(self.cfg.get("safety_override", True)):
                cap = max(5.0, min(100.0, float(self.cfg.get("safety_score_cap", 45.0) or 45.0)))
                scores["safety"] = round(min(_num(scores.get("safety"), 100.0), cap), 1)
                applied = True
            else:
                reason = "safety_override_disabled"
        elif rec_need == "balance" and bool(self.cfg.get("annotate_only_for_balance", True)):
            applied = False
            reason = "balance_annotate_only"
        else:
            current = _num(scores.get(rec_need), 0.0)
            scores[rec_need] = round(min(100.0, current + boost), 1)
            applied = True

        need, goal, priority = self._choose_goal(scores, rec_need, rec_goal)
        needs["scores"] = {k: round(_num(v), 1) for k, v in scores.items()}
        if applied:
            needs["dominant_need"] = need
            needs["recommended_goal"] = goal
            needs["confidence"] = max(_num(needs.get("confidence"), 0.55), round(confidence, 2))
        reasons = dict(_as_dict(needs.get("reasons")))
        marker = {
            **base_reason,
            "available": True,
            "applied": bool(applied),
            "reason": reason,
            "memory_need": rec_need,
            "memory_goal": rec_goal or GOAL_BY_NEED[rec_need][0],
            "memory_priority": rec_priority or priority,
            "confidence": round(confidence, 4),
            "boost": boost,
            "previous_need": previous_need,
            "previous_goal": previous_goal,
            "result_need": needs.get("dominant_need"),
            "result_goal": needs.get("recommended_goal"),
            "top_item": shadow.get("top_item", {}),
            "score_before": round(before_scores.get(rec_need if rec_need != "safety" else "safety", 0.0), 1),
            "score_after": round(_num(scores.get(rec_need if rec_need != "safety" else "safety"), 0.0), 1),
        }
        reasons["memory_bias"] = marker
        needs["reasons"] = reasons
        needs["memory_bias"] = marker
        self._last = marker
        return needs

    def _choose_goal(self, scores: Dict[str, Any], memory_need: str, memory_goal: str) -> Tuple[str, str, str]:
        safety = _num(scores.get("safety"), 100.0)
        if safety < 55.0:
            return "safety", "pause_and_observe", "critical"
        if _num(scores.get("rest"), 0.0) >= 72.0:
            return "rest", "rest_quietly", "low"
        if _num(scores.get("social"), 0.0) >= 70.0:
            return "social", "seek_owner_or_invite_interaction", "normal"
        if _num(scores.get("exploration"), 0.0) >= 68.0:
            return "exploration", "look_around_and_learn", "normal"
        if _num(scores.get("boredom"), 0.0) >= 60.0:
            return "boredom", "choose_idle_activity", "normal"
        if _num(scores.get("curiosity"), 0.0) >= 65.0:
            return "curiosity", "inspect_environment", "normal"
        if memory_need == "balance":
            return "balance", "calm_idle", "low"
        return "balance", "calm_idle", "low"

    @staticmethod
    def _attach(needs: Dict[str, Any], marker: Dict[str, Any]) -> None:
        reasons = dict(_as_dict(needs.get("reasons")))
        reasons["memory_bias"] = marker
        needs["reasons"] = reasons
        needs["memory_bias"] = marker
