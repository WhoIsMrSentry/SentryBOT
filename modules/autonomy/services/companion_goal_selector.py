from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_companion_core import PetCompanionCore

PET_COMPANION_GOAL_SELECTOR_INTEGRATION_CONTRACT = True
PET_COMPANION_GOAL_SELECTOR_INTEGRATION_ROLE = "pet_core_side_channel_for_goal_selector"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalSelector:
    """Turn companion needs into a semantic goal plan.

    This class does not drive hardware. It produces a safe, inspectable plan
    that can later be executed by capability/safety layers. This keeps the
    companion behavior semantic: needs -> goal -> expression/capability plan.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "event_cooldown_s": 12.0,
        "auto_execute": True,
        "pet_companion_enabled": True,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self.enabled = bool(self.cfg.get("enabled", True))
        self._last_event_ts: float = 0.0
        self._last_plan_key: str = ""
        environment_policy = _as_dict(self.cfg.get("environment_policy"))
        try:
            seed = int(environment_policy.get("seed", 0))
        except (TypeError, ValueError):
            seed = 0
        self._rng = random.Random(seed)
        
        try:
            from modules.autonomy.services.behavior_planner import BehaviorPlanner
            self.behavior_planner = BehaviorPlanner(self.cfg)
        except ImportError:
            self.behavior_planner = None

    def select(
        self,
        needs_snapshot: Optional[Dict[str, Any]],
        *,
        owner_present: bool = False,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        snap = _as_dict(needs_snapshot)
        dominant = str(snap.get("dominant_need") or "balance").strip().lower()
        recommended = str(snap.get("recommended_goal") or "calm_idle").strip().lower()
        confidence = max(0.0, min(1.0, _as_float(snap.get("confidence"), 0.55)))
        scores = dict(_as_dict(snap.get("scores")))
        learning = self._learning_context(snap)
        for need, adjustment in learning.get("candidate_weight_adjustments", {}).items():
            if need in scores:
                scores[need] = max(0.0, _as_float(scores.get(need)) + _as_float(adjustment))

        plan = self._plan_for(dominant, recommended, scores=scores, owner_present=owner_present, snapshot=snap)
        pet_companion = self._pet_companion_decision(
            snap,
            dominant=dominant,
            recommended=recommended,
            scores=scores,
            owner_present=owner_present,
        )
        plan = self._merge_pet_companion_plan(plan, pet_companion)
        plan_key = f"{dominant}:{recommended}:{plan.get('behavior')}"
        event = self._event_for(plan_key, dominant, ts)

        auto_execute = bool(self.cfg.get("auto_execute", True))

        out: Dict[str, Any] = {
            "ok": True,
            "available": bool(self.enabled),
            "timestamp": ts,
            "plan_id": plan_key,
            "dominant_need": dominant,
            "recommended_goal": recommended,
            "behavior": plan.get("behavior", "calm_idle"),
            "pet_companion": pet_companion,
            "pet_intent": str(pet_companion.get("intent") or ""),
            "pet_expression_hint": str(pet_companion.get("expression_hint") or ""),
            "pet_motion_hint": str(pet_companion.get("motion_hint") or ""),
            "pet_speech_hint": str(pet_companion.get("speech_hint") or ""),
            "pet_goal_hints": list(pet_companion.get("goal_hints") or []),
            "pet_needs_bias": dict(pet_companion.get("needs_bias") or {}),
            "pet_memory_tags": list(pet_companion.get("memory_tags") or []),
            "priority": plan.get("priority", "low"),
            "confidence": round(confidence, 2),
            "reason": f"needs.{dominant}",
            "event": event,
            "expression_event": plan.get("expression_event", f"needs.{dominant}"),
            "expression_data": {
                "recommended_goal": recommended,
                "confidence": round(confidence, 2),
                "dominant_need": dominant,
            },
            "actions": plan.get("actions", []),
            "safe_to_execute": bool(plan.get("safe_to_execute", True)),
            "auto_execute": auto_execute,
            "owner_present": bool(owner_present),
            "scores": {k: round(_as_float(v), 1) for k, v in scores.items()},
        }
        out = self._apply_environment_policy(out, snapshot=snap, owner_present=owner_present, timestamp=ts)
        out = self._apply_uncertainty_policy(out, snapshot=snap)
        out = self._apply_personalization_policy(out, snapshot=snap)
        out = self._apply_privacy_policy(out, snapshot=snap)
        out = self._apply_capability_health_policy(out, snapshot=snap)
        out = self._apply_outcome_learning_policy(out, snapshot=snap)
        out = self._apply_social_policy(out, snapshot=snap, owner_present=owner_present)
        out["config_source"] = {
            "root": "companion_goals",
            "policies": {
                "uncertainty": "companion_goals.autonomy_policy.uncertainty",
                "personalization": "companion_goals.autonomy_policy.personalization",
                "privacy": "companion_goals.autonomy_policy.privacy",
                "explanation": "companion_goals.autonomy_policy.explanation",
                "capability_health": "companion_goals.autonomy_policy.health",
                "environment": "companion_goals.environment_policy",
                "outcome_learning": "outcome_learning",
                "social": "social_policy",
                "pet_companion": "companion_goals.pet_companion_enabled",
            },
        }
        return self._apply_explanation_policy(out)



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

    def _learning_context(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(self.cfg.get("outcome_learning"))
        if not bool(policy.get("enabled", False)):
            return {}
        reflection = _as_dict(snapshot.get("reflection_policy") or snapshot.get("reflection"))
        outcome = _as_dict(snapshot.get("outcome_learning") or snapshot.get("last_outcome"))
        raw_adjustments = _as_dict(reflection.get("candidate_weight_adjustments") or outcome.get("candidate_weight_adjustments"))
        limit = _as_float(policy.get("max_weight_adjustment"), 0.0)
        adjustments = {}
        for key, value in raw_adjustments.items():
            parsed = _as_float(value)
            if limit > 0.0:
                parsed = max(-limit, min(limit, parsed))
            adjustments[str(key)] = parsed
        return {
            "candidate_weight_adjustments": adjustments,
            "temporary_avoid_tags": [str(tag) for tag in (reflection.get("temporary_avoid_tags") or outcome.get("temporary_avoid_tags") or []) if str(tag)],
            "preferred_contexts": _as_dict(reflection.get("preferred_contexts") or outcome.get("preferred_contexts")),
        }

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

    def _pet_companion_decision(
        self,
        snap: Dict[str, Any],
        *,
        dominant: str,
        recommended: str,
        scores: Dict[str, Any],
        owner_present: bool,
    ) -> Dict[str, Any]:
        if not bool(self.cfg.get("pet_companion_enabled", True)):
            return {}
        score_map = _as_dict(scores)
        pet_needs = {
            "safety": _as_float(score_map.get("safety"), 0.0),
            "social": _as_float(score_map.get("social"), 0.0),
            "curiosity": _as_float(score_map.get("curiosity"), 0.0),
            "boredom": _as_float(score_map.get("boredom"), 0.0),
            "energy": _as_float(score_map.get("energy"), _as_float(snap.get("energy"), 0.7)),
            "dominant_need": dominant,
            "recommended_goal": recommended,
        }
        if dominant == "exploration":
            pet_needs["curiosity"] = max(pet_needs["curiosity"], 0.65)
        elif dominant == "rest":
            pet_needs["energy"] = min(pet_needs["energy"], 0.2)
        elif dominant == "social":
            pet_needs["social"] = max(pet_needs["social"], 0.65)
        elif dominant == "safety":
            pet_needs["safety"] = max(pet_needs["safety"], 0.75)
        elif dominant == "boredom":
            pet_needs["boredom"] = max(pet_needs["boredom"], 0.7)
        elif dominant == "curiosity":
            pet_needs["curiosity"] = max(pet_needs["curiosity"], 0.7)

        context = {
            "needs": pet_needs,
            "bond": _as_dict(snap.get("bond")),
            "routine": _as_dict(snap.get("routine")),
            "perception": {
                **_as_dict(snap.get("perception")),
                "owner_present": bool(owner_present),
            },
        }
        return PetCompanionCore().decide(context).as_dict()

    def _merge_pet_companion_plan(self, plan: Dict[str, Any], pet_companion: Dict[str, Any]) -> Dict[str, Any]:
        if not pet_companion:
            return plan
        out = dict(plan)
        actions = list(out.get("actions") or [])
        actions.append(
            {
                "type": "pet_intent",
                "name": str(pet_companion.get("intent") or ""),
                "expression_hint": str(pet_companion.get("expression_hint") or ""),
                "motion_hint": str(pet_companion.get("motion_hint") or ""),
                "speech_hint": str(pet_companion.get("speech_hint") or ""),
                "goal_hints": list(pet_companion.get("goal_hints") or []),
                "risk": "semantic",
            }
        )
        out["actions"] = actions
        out["pet_companion"] = pet_companion
        return out

    def _plan_for(self, dominant: str, recommended: str, *, scores: Dict[str, Any], owner_present: bool, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if recommended == "llm_behavior_planning" and self.behavior_planner:
            # The planner holds a queue of actions to avoid spamming the LLM
            next_action = self.behavior_planner.get_next_action()
            if not next_action:
                # Need a new plan
                # Pass a dummy vision context or ideally the real one if we had it
                recent_ref = snapshot.get("recent_reflections", []) if snapshot else []
                tool_schemas = snapshot.get("tool_schemas", []) if snapshot else []
                new_plan = self.behavior_planner.generate_plan(snapshot or {}, "Robot is currently idle.", recent_reflections=recent_ref, tool_schemas=tool_schemas)
                if new_plan:
                    next_action = self.behavior_planner.get_next_action()
            
            if next_action:
                # Construct a semantic plan from the LLM action
                # E.g. {"tool": "speak", "text": "...", "tone": "tired"} -> action array
                return {
                    "behavior": "llm_generated_action",
                    "priority": "normal",
                    "expression_event": f"needs.{dominant}",
                    "safe_to_execute": True,
                    "actions": [next_action] # The arbiter will execute this raw tool call
                }
                
        if dominant == "safety":
            return {
                "behavior": "pause_and_observe",
                "priority": "critical",
                "expression_event": "needs.safety",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.safety"},
                    {"type": "motion", "name": "freeze", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "safety"},
                ],
            }
        if recommended == "rest_in_safe_place" or dominant == "rest":
            return {
                "behavior": "rest_in_safe_place",
                "priority": "low",
                "expression_event": "needs.rest",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.rest"},
                    {"type": "navigation", "name": "rest_corner", "risk": "low"},
                    {"type": "pose", "name": "sleepy_idle", "risk": "low"},
                    {"type": "speech", "mode": "silent"},
                ],
            }
        if dominant == "social":
            return {
                "behavior": "seek_owner_or_invite_interaction" if not owner_present else "engage_owner",
                "priority": "normal",
                "expression_event": "needs.social",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.social"},
                    {"type": "perception", "name": "owner_scan", "risk": "low"},
                    {"type": "speech", "mode": "short_prompt", "template": "social_invite"},
                ],
            }
        if dominant == "exploration":
            return {
                "behavior": "look_around_and_learn",
                "priority": "normal",
                "expression_event": "needs.exploration",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.exploration"},
                    {"type": "vision", "mode": "cheap", "reason": "exploration"},
                    {"type": "motion", "name": "look_around", "risk": "low"},
                ],
            }
        if recommended == "look_for_company_or_rest" or dominant == "boredom":
            return {
                "behavior": "scan_for_company_then_rest",
                "priority": "normal",
                "expression_event": "needs.boredom",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.boredom"},
                    {"type": "motion", "name": "stretch_or_scan", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "boredom"},
                    {"type": "perception", "name": "track_person", "label": "person", "strategy": "center", "risk": "low"},
                    {"type": "memory", "name": "observe", "kind": "episode", "summary": "Robot was bored and scanned for company.", "risk": "none"},
                ],
            }
        if recommended == "inspect_sound_source":
            return {
                "behavior": "inspect_sound_source",
                "priority": "high",
                "expression_event": "needs.sound_attention",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.sound_attention"},
                    {"type": "motion", "name": "attend", "risk": "low"},
                    {"type": "perception", "name": "track_person", "label": "person", "strategy": "center", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "sound_interrupt"},
                ],
            }
        if dominant == "curiosity":
            return {
                "behavior": "inspect_environment_and_learn",
                "priority": "normal",
                "expression_event": "needs.curiosity",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.curiosity"},
                    {"type": "vision", "mode": "cheap", "reason": "curiosity"},
                    {"type": "vision", "mode": "semantic", "reason": "curiosity_unknown"},
                    {"type": "motion", "name": "attend", "risk": "low"},
                ],
            }
        return {
            "behavior": "calm_idle",
            "priority": "low",
            "expression_event": "needs.balance",
            "safe_to_execute": True,
            "actions": [
                {"type": "expression", "event": "needs.balance"},
                {"type": "wait", "label": "calm_idle", "risk": "none"},
            ],
        }

    def _event_for(self, plan_key: str, dominant: str, now_ts: float) -> str:
        if not self.enabled:
            return ""
        cooldown = max(1.0, _as_float(self.cfg.get("event_cooldown_s"), 12.0))
        if plan_key == self._last_plan_key and (now_ts - self._last_event_ts) < cooldown:
            return ""
        self._last_plan_key = plan_key
        self._last_event_ts = now_ts
        return f"goal.{dominant}"
