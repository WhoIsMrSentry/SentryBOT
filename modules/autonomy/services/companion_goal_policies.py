from __future__ import annotations

import logging
from typing import Any, Dict, List

from modules.autonomy.services.needs_engine import extract_risk_and_safety, is_pct_scale_scores

logger = logging.getLogger("autonomy.companion_goal_policies")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_dot_path(root: Any, path: str) -> Any:
    current: Any = root
    for part in str(path or "").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _suppress_action_types(actions: Any, suppressed: set[str]) -> tuple[List[Any], List[Dict[str, str]]]:
    items = actions if isinstance(actions, list) else []
    kept: List[Any] = []
    removed: List[Dict[str, str]] = []
    for action in items:
        action_type = str(action.get("type") or "").strip() if isinstance(action, dict) else ""
        if action_type in suppressed:
            removed.append({"type": action_type})
        else:
            kept.append(action)
    return kept, removed


def _ensure_semantic_expression(out: Dict[str, Any], semantic: str, source: str) -> None:
    sem = str(semantic or "").strip()
    if not sem:
        return
    out["pet_expression_hint"] = sem
    actions = out.get("actions")
    if not isinstance(actions, list):
        actions = []
        out["actions"] = actions
    if not any(isinstance(action, dict) and str(action.get("semantic") or "") == sem for action in actions):
        actions.append({"type": "expression", "event": f"semantic.{sem}", "semantic": sem, "source": source})


class CompanionGoalPoliciesMixin:
    """Policy rules (social, environment, privacy, health, learning) for CompanionGoalSelector."""

    cfg: Dict[str, Any]
    _rng: Any

    def _apply_social_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any], owner_present: bool) -> Dict[str, Any]:
        policy = _as_dict(self.cfg.get("social_policy"))
        if not bool(policy.get("enabled", False)):
            return out
        perception = _as_dict(snapshot.get("perception"))
        scene = _as_dict(snapshot.get("scene"))
        people = perception.get("people") or scene.get("people") or []
        people = people if isinstance(people, list) else []
        if len(people) > 1:
            person_type = "multiple_people"
        elif owner_present:
            person_type = "owner"
        elif people and isinstance(people[0], dict):
            person_type = str(people[0].get("person_type") or people[0].get("relationship_type") or "unknown_guest")
        else:
            person_type = "unknown_guest"
        profile = _as_dict(_as_dict(policy.get("person_types")).get(person_type))
        restricted = {str(value) for value in (profile.get("restricted_action_types") or []) if str(value)}
        actions = list(out.get("actions") or [])
        allowed_actions = [action for action in actions if not isinstance(action, dict) or str(action.get("type") or "") not in restricted]
        suppressed_actions = len(allowed_actions) != len(actions)
        out["actions"] = allowed_actions
        out["social_guard"] = {
            "person_type": person_type,
            "people_count": len(people),
            "restricted_action_types": sorted(restricted),
            "suppressed_actions": suppressed_actions,
            "default_behavior": str(policy.get("default_behavior") or ""),
        }
        if suppressed_actions or not bool(profile.get("auto_execute", True)):
            out["auto_execute"] = False
            out["social_guard"]["reason"] = "social_permission_required"
            out["pet_expression_hint"] = str(profile.get("semantic") or policy.get("safe_semantic") or out.get("pet_expression_hint") or "")
        return out

    def _apply_outcome_learning_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        learning = self._learning_context(snapshot)
        if not learning:
            return out
        out["outcome_learning"] = learning
        avoid_tags = set(learning.get("temporary_avoid_tags") or [])
        plan_tags = {str(tag) for tag in (_as_dict(out.get("pet_companion")).get("tags") or [])}
        if avoid_tags.intersection(plan_tags):
            out["auto_execute"] = False
            out["suppressed"] = True
            out["suppression_reason"] = "temporary_outcome_avoidance"
            out["pet_expression_hint"] = str(_as_dict(self.cfg.get("outcome_learning")).get("safe_semantic") or out.get("pet_expression_hint") or "")
        return out

    def _apply_capability_health_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy_root = self.cfg.get("autonomy_policy", {})
        policy_root = policy_root if isinstance(policy_root, dict) else {}
        gate = policy_root.get("capability_gate", {})
        gate = gate if isinstance(gate, dict) else {}
        health_policy = _as_dict(policy_root.get("health"))
        snapshot_path = str(gate.get("snapshot_path") or "capability_health")
        health = _as_dict(snapshot.get(snapshot_path))
        actions = out.get("actions", [])
        actions = actions if isinstance(actions, list) else []
        removed = []
        if bool(health_policy.get("enabled", False)) and health and not bool(health.get("ok", False)):
            suppressed = {str(item).strip() for item in health_policy.get("suppress_action_types", []) if str(item).strip()}
            actions, dropped = _suppress_action_types(actions, suppressed)
            for item in dropped:
                removed.append({**item, "reason": str(health_policy.get("reason") or "")})
        if bool(gate.get("enabled", False)) and health:
            capabilities = _as_dict(health.get("capabilities"))
            requirements = _as_dict(gate.get("default_required"))
            kept = []
            for action in actions:
                action_type = str(action.get("type") or "") if isinstance(action, dict) else ""
                required = requirements.get(action_type, [])
                required = required if isinstance(required, list) else [required]
                unavailable = [str(name) for name in required if not bool((capabilities.get(str(name), {}) or {}).get("available", False))]
                if unavailable:
                    removed.append({"type": action_type, "reason": str(gate.get("reason") or ""), "missing": unavailable})
                else:
                    kept.append(action)
            actions = kept
        out["actions"] = actions
        if removed:
            semantic = str(gate.get("fallback_semantic") or health_policy.get("fallback_semantic") or "").strip()
            _ensure_semantic_expression(out, semantic, "capability_health_policy")
            out["capability_guard"] = {
                "reason": str(gate.get("reason") or health_policy.get("reason") or ""),
                "removed_actions": removed,
                "unavailable_components": health.get("unavailable_components", []),
            }
        return out

    def _apply_privacy_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(_as_dict(self.cfg.get("autonomy_policy")).get("privacy"))
        if not bool(policy.get("enabled", False)):
            return out
        restricted = {str(item).strip() for item in policy.get("restricted_zones", []) if str(item).strip()}
        zones = [
            str(val).strip()
            for path in policy.get("restricted_zone_paths", [])
            if (val := _resolve_dot_path(snapshot, str(path))) is not None
        ]
        guest_present = any(bool(_resolve_dot_path(snapshot, str(path))) for path in policy.get("guest_paths", []))
        if not (bool(restricted.intersection(zones)) or guest_present):
            return out
        suppressed = {str(item).strip() for item in policy.get("suppress_action_types", []) if str(item).strip()}
        out["actions"], _ = _suppress_action_types(out.get("actions", []), suppressed)
        out["privacy"] = {
            "reason": str(policy.get("reason") or ""),
            "zones": zones,
            "guest_present": guest_present,
            "suppressed_action_types": sorted(suppressed),
        }
        return out

    def _apply_explanation_policy(self, out: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(_as_dict(self.cfg.get("autonomy_policy")).get("explanation"))
        if not bool(policy.get("enabled", False)):
            return out
        fields = [str(field).strip() for field in policy.get("include", []) if str(field).strip()]
        out["decision_explanation"] = {field: out.get(field) for field in fields if field in out}
        return out

    def _apply_personalization_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(_as_dict(self.cfg.get("autonomy_policy")).get("personalization"))
        if not bool(policy.get("enabled", False)):
            return out
        applied = []
        for rule in policy.get("rules", []):
            if not isinstance(rule, dict):
                continue
            expected = rule.get("when", True)
            if not any(_resolve_dot_path(snapshot, str(path)) == expected for path in rule.get("signal_paths", [])):
                continue
            suppressed = {str(item).strip() for item in rule.get("suppress_action_types", []) if str(item).strip()}
            out["actions"], _ = _suppress_action_types(out.get("actions", []), suppressed)
            _ensure_semantic_expression(out, str(rule.get("semantic") or ""), "personalization_policy")
            applied.append({
                "reason": str(rule.get("reason") or ""),
                "suppressed_action_types": sorted(suppressed),
            })
        if applied:
            out["personalization"] = applied
        return out

    def _apply_uncertainty_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(_as_dict(self.cfg.get("autonomy_policy")).get("uncertainty"))
        if not bool(policy.get("enabled", False)):
            return out
        values = []
        for path in policy.get("confidence_paths", []):
            current = _resolve_dot_path(snapshot, str(path))
            if current is None:
                continue
            try:
                values.append(float(current))
            except (TypeError, ValueError):
                continue
        if not values:
            return out
        threshold = _as_float(policy.get("hold_below"), 0.0)
        observed_confidence = min(values)
        if observed_confidence >= threshold:
            return out
        suppressed = {str(item).strip() for item in policy.get("suppress_action_types", []) if str(item).strip()}
        out["actions"], _ = _suppress_action_types(out.get("actions", []), suppressed)
        _ensure_semantic_expression(out, str(policy.get("fallback_semantic") or ""), "uncertainty_policy")
        out["autonomy_guard"] = {
            "reason": str(policy.get("reason") or ""),
            "observed_confidence": observed_confidence,
            "threshold": threshold,
            "suppressed_action_types": sorted(suppressed),
        }
        return out

    @staticmethod
    def _policy_value(context: Dict[str, Any], path: str) -> float:
        current = _resolve_dot_path(context, path)
        if isinstance(current, bool):
            return 1.0 if current else 0.0
        return _as_float(current, 0.0)

    def _apply_environment_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any], owner_present: bool, timestamp: float) -> Dict[str, Any]:
        policy = _as_dict(self.cfg.get("environment_policy"))
        if not bool(policy.get("enabled", False)):
            return out
        raw_scores = _as_dict(snapshot.get("normalized_scores") or out.get("scores"))
        risk_val, safety_level = extract_risk_and_safety(snapshot, _as_dict(out.get("scores")))
        env_scores = dict(raw_scores)
        if is_pct_scale_scores(snapshot, _as_dict(out.get("scores"))):
            # Expose risk as scores.safety to keep 0..1 hazard semantics consistent with safety_hold_threshold
            env_scores["safety"] = risk_val
            env_scores["safety_level"] = safety_level
        env_scores.setdefault("risk", risk_val)
        context = {
            "scores": env_scores,
            "risk": risk_val,
            "safety_level": safety_level,
            "needs": _as_dict(snapshot.get("needs")),
            "perception": {**_as_dict(snapshot.get("perception")), "owner_present": bool(owner_present)},
        }
        signals: Dict[str, float] = {}
        for signal, paths in _as_dict(policy.get("signals")).items():
            candidates = paths if isinstance(paths, list) else [paths]
            signals[str(signal)] = max((self._policy_value(context, str(path)) for path in candidates), default=0.0)
        safety_hold = _as_float(policy.get("safety_hold_threshold"), 1.0)
        if signals.get("safety", 0.0) >= safety_hold:
            out["environmental_choice"] = {"reason": "safety_hold", "signals": signals}
            return out
        scored: list[tuple[str, float, Dict[str, Any]]] = []
        for name, raw in _as_dict(policy.get("candidates")).items():
            candidate = _as_dict(raw)
            score = _as_float(candidate.get("base"), 0.0)
            for signal, weight in _as_dict(candidate.get("weights")).items():
                score += signals.get(str(signal), 0.0) * _as_float(weight, 0.0)
            scored.append((str(name), score, candidate))
        if not scored:
            return out
        scored.sort(key=lambda item: (-item[1], item[0]))
        chosen = scored[0]
        band = max(0.0, _as_float(policy.get("exploration_band"), 0.0))
        near_best = [item for item in scored if chosen[1] - item[1] <= band]
        if len(near_best) > 1 and self._rng.random() < _as_float(policy.get("exploration_probability"), 0.0):
            chosen = self._rng.choice(near_best)
        name, score, candidate = chosen
        semantic = str(candidate.get("semantic") or out.get("pet_expression_hint") or "ambient_idle")
        out["behavior"] = str(candidate.get("behavior") or out.get("behavior") or "calm_idle")
        out["recommended_goal"] = str(candidate.get("recommended_goal") or out.get("recommended_goal") or "")
        out["pet_expression_hint"] = semantic
        actions = list(out.get("actions") or [])
        for output in candidate.get("outputs", []):
            if not isinstance(output, dict):
                continue
            materialized = dict(output)
            materialized["source"] = "environment_policy"
            actions.append(materialized)
        actions.append({"type": "expression", "event": f"semantic.{semantic}", "semantic": semantic, "risk": "none"})
        out["actions"] = actions
        out["environmental_choice"] = {
            "candidate": name,
            "score": round(score, 4),
            "signals": {key: round(value, 4) for key, value in signals.items()},
            "timestamp": timestamp,
        }
        return out
