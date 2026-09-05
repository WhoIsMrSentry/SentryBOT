from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.companion_goal_policies")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        health_policy = policy_root.get("health", {})
        health_policy = health_policy if isinstance(health_policy, dict) else {}
        snapshot_path = str(gate.get("snapshot_path") or "capability_health")
        health = snapshot.get(snapshot_path, {})
        health = health if isinstance(health, dict) else {}
        actions = out.get("actions", [])
        actions = actions if isinstance(actions, list) else []
        removed = []
        if bool(health_policy.get("enabled", False)) and health and not bool(health.get("ok", False)):
            suppressed = {str(item).strip() for item in health_policy.get("suppress_action_types", []) if str(item).strip()}
            kept = []
            for action in actions:
                action_type = str(action.get("type") or "") if isinstance(action, dict) else ""
                if action_type in suppressed:
                    removed.append({"type": action_type, "reason": str(health_policy.get("reason") or "")})
                else:
                    kept.append(action)
            actions = kept
        if bool(gate.get("enabled", False)) and health:
            capabilities = health.get("capabilities", {})
            capabilities = capabilities if isinstance(capabilities, dict) else {}
            requirements = gate.get("default_required", {})
            requirements = requirements if isinstance(requirements, dict) else {}
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
            if semantic and not any(isinstance(action, dict) and str(action.get("semantic") or "") == semantic for action in actions):
                actions.append({"type": "expression", "event": f"semantic.{semantic}", "semantic": semantic, "source": "capability_health_policy"})
                out["pet_expression_hint"] = semantic
            out["capability_guard"] = {
                "reason": str(gate.get("reason") or health_policy.get("reason") or ""),
                "removed_actions": removed,
                "unavailable_components": health.get("unavailable_components", []),
            }
        return out

    def _apply_privacy_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy_root = self.cfg.get("autonomy_policy", {})
        policy_root = policy_root if isinstance(policy_root, dict) else {}
        policy = policy_root.get("privacy", {})
        policy = policy if isinstance(policy, dict) else {}
        if not bool(policy.get("enabled", False)):
            return out
        restricted = {str(item).strip() for item in policy.get("restricted_zones", []) if str(item).strip()}
        zones = []
        for path in policy.get("restricted_zone_paths", []):
            current: Any = snapshot
            for part in str(path).split("."):
                current = current.get(part) if isinstance(current, dict) else None
            if current is not None:
                zones.append(str(current).strip())
        guest_present = False
        for path in policy.get("guest_paths", []):
            current: Any = snapshot
            for part in str(path).split("."):
                current = current.get(part) if isinstance(current, dict) else None
            guest_present = guest_present or bool(current)
        restricted_context = bool(restricted.intersection(zones)) or guest_present
        if not restricted_context:
            return out
        suppressed = {str(item).strip() for item in policy.get("suppress_action_types", []) if str(item).strip()}
        actions = out.get("actions", [])
        actions = actions if isinstance(actions, list) else []
        out["actions"] = [action for action in actions if not isinstance(action, dict) or str(action.get("type") or "").strip() not in suppressed]
        out["privacy"] = {
            "reason": str(policy.get("reason") or ""),
            "zones": zones,
            "guest_present": guest_present,
            "suppressed_action_types": sorted(suppressed),
        }
        return out

    def _apply_explanation_policy(self, out: Dict[str, Any]) -> Dict[str, Any]:
        policy_root = self.cfg.get("autonomy_policy", {})
        policy_root = policy_root if isinstance(policy_root, dict) else {}
        policy = policy_root.get("explanation", {})
        policy = policy if isinstance(policy, dict) else {}
        if not bool(policy.get("enabled", False)):
            return out
        fields = [str(field).strip() for field in policy.get("include", []) if str(field).strip()]
        out["decision_explanation"] = {field: out.get(field) for field in fields if field in out}
        return out

    def _apply_personalization_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy_root = self.cfg.get("autonomy_policy", {})
        policy_root = policy_root if isinstance(policy_root, dict) else {}
        policy = policy_root.get("personalization", {})
        policy = policy if isinstance(policy, dict) else {}
        if not bool(policy.get("enabled", False)):
            return out
        applied = []
        for rule in policy.get("rules", []):
            if not isinstance(rule, dict):
                continue
            expected = rule.get("when", True)
            matched = False
            for path in rule.get("signal_paths", []):
                current: Any = snapshot
                for part in str(path).split("."):
                    current = current.get(part) if isinstance(current, dict) else None
                if current == expected:
                    matched = True
                    break
            if not matched:
                continue
            suppressed = {str(item).strip() for item in rule.get("suppress_action_types", []) if str(item).strip()}
            actions = out.get("actions", [])
            actions = actions if isinstance(actions, list) else []
            out["actions"] = [action for action in actions if not isinstance(action, dict) or str(action.get("type") or "").strip() not in suppressed]
            semantic = str(rule.get("semantic") or "").strip()
            if semantic:
                out["pet_expression_hint"] = semantic
                if not any(isinstance(action, dict) and str(action.get("semantic") or "") == semantic for action in out["actions"]):
                    out["actions"].append({"type": "expression", "event": f"semantic.{semantic}", "semantic": semantic, "source": "personalization_policy"})
            applied.append({
                "reason": str(rule.get("reason") or ""),
                "suppressed_action_types": sorted(suppressed),
            })
        if applied:
            out["personalization"] = applied
        return out

    def _apply_uncertainty_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy_root = self.cfg.get("autonomy_policy", {})
        policy_root = policy_root if isinstance(policy_root, dict) else {}
        policy = policy_root.get("uncertainty", {})
        policy = policy if isinstance(policy, dict) else {}
        if not bool(policy.get("enabled", False)):
            return out
        values = []
        for path in policy.get("confidence_paths", []):
            current: Any = snapshot
            for part in str(path).split("."):
                current = current.get(part) if isinstance(current, dict) else None
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
        actions = out.get("actions", [])
        actions = actions if isinstance(actions, list) else []
        out["actions"] = [action for action in actions if not isinstance(action, dict) or str(action.get("type") or "").strip() not in suppressed]
        semantic = str(policy.get("fallback_semantic") or "").strip()
        if semantic:
            out["pet_expression_hint"] = semantic
            if not any(isinstance(action, dict) and str(action.get("semantic") or "") == semantic for action in out["actions"]):
                out["actions"].append({"type": "expression", "event": f"semantic.{semantic}", "semantic": semantic, "source": "uncertainty_policy"})
        out["autonomy_guard"] = {
            "reason": str(policy.get("reason") or ""),
            "observed_confidence": observed_confidence,
            "threshold": threshold,
            "suppressed_action_types": sorted(suppressed),
        }
        return out

    @staticmethod
    def _policy_value(context: Dict[str, Any], path: str) -> float:
        current: Any = context
        for token in str(path or "").split("."):
            if not isinstance(current, dict):
                return 0.0
            current = current.get(token)
        if isinstance(current, bool):
            return 1.0 if current else 0.0
        return _as_float(current, 0.0)

    def _apply_environment_policy(self, out: Dict[str, Any], *, snapshot: Dict[str, Any], owner_present: bool, timestamp: float) -> Dict[str, Any]:
        policy = _as_dict(self.cfg.get("environment_policy"))
        if not bool(policy.get("enabled", False)):
            return out
        context = {
            "scores": _as_dict(out.get("scores")),
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
