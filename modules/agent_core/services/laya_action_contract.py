"""Fail-closed conversion of typed Laya choices into inert action proposals."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


LIGHT_COLORS = (
    "red", "green", "blue", "yellow", "orange", "purple", "pink",
    "cyan", "teal", "magenta", "white", "off",
)
LIGHT_EFFECTS = (
    "COMET", "PULSE", "WAVE", "SOLID", "OFF", "BREATHE",
    "RANDOM_BLINK", "TWINKLE",
)
_UNSPECIFIED = "unspecified"


def get_laya_action_questions() -> Dict[str, Dict[str, Any]]:
    """Return finite choice questions; no free-form actuator values are requested."""
    return {
        "action_color": {
            "type": "choice",
            "instructions": "Işık komutunda kullanıcının istediği renk hangisi?",
            "criteria": {
                **{color: f"{color} rengi" for color in LIGHT_COLORS},
                _UNSPECIFIED: "Kullanıcı bir renk belirtmedi veya istek ışık rengi değil",
            },
        },
        "action_effect": {
            "type": "choice",
            "instructions": "Işık komutunda kullanıcı hangi animasyon efektini istiyor?",
            "criteria": {
                **{effect: f"{effect.lower()} ışık animasyonu" for effect in LIGHT_EFFECTS},
                _UNSPECIFIED: "Kullanıcı bir animasyon belirtmedi",
            },
        },
    }


def build_laya_action_proposal(
    *,
    target_module: str,
    module_confidence: Any,
    is_direct_command: bool,
    direct_confidence: Any,
    answers: Any,
    policy: Any,
) -> Optional[Dict[str, Any]]:
    """Build an inert set_lights proposal only when all policy checks pass.

    This function never dispatches a tool or touches hardware. The feature is
    opt-in and its caller must keep proposal creation separate from execution.
    """
    if not isinstance(policy, dict) or not policy.get("enabled", False):
        return None
    allowed = policy.get("allowed_actions", [])
    if not isinstance(allowed, list) or "set_lights" not in allowed:
        return None
    if target_module != "neopixel" or is_direct_command is not True:
        return None

    threshold = _confidence(policy.get("confidence_threshold"))
    confidences = (
        _confidence(module_confidence),
        _confidence(direct_confidence),
    )
    if threshold is None or any(value is None or value < threshold for value in confidences):
        return None
    if not isinstance(answers, dict):
        return None

    color, color_conf = _choice_answer(answers.get("action_color"))
    effect, effect_conf = _choice_answer(answers.get("action_effect"))
    if color not in LIGHT_COLORS or effect not in (*LIGHT_EFFECTS, _UNSPECIFIED):
        return None
    if color_conf is None or effect_conf is None or color_conf < threshold or effect_conf < threshold:
        return None

    if effect == _UNSPECIFIED:
        effect = policy.get("default_light_effect")
    if effect not in LIGHT_EFFECTS:
        return None

    proposal_confidence = min(*confidences, color_conf, effect_conf)
    return {
        "schema_version": 1,
        "tool_name": "set_lights",
        "arguments": {"effect": effect, "color": color},
        "confidence": proposal_confidence,
    }


def _choice_answer(answer: Any) -> tuple[Optional[str], Optional[float]]:
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None, None
    choice = answer.get("choice")
    confidence = _confidence(answer.get("confidence"))
    if not isinstance(choice, str):
        return None, None
    return choice, confidence


def bind_laya_action_proposal(
    proposal: Any, request_id: Any
) -> Optional[Dict[str, Any]]:
    """Bind an inert proposal to the request that produced it."""
    if not isinstance(proposal, dict) or not isinstance(request_id, str) or not request_id.strip():
        return None
    if "request_id" in proposal and proposal["request_id"] != request_id:
        return None
    if not isinstance(proposal.get("arguments"), dict):
        return None
    bound = dict(proposal)
    bound["arguments"] = dict(proposal["arguments"])
    bound["request_id"] = request_id
    return bound


def validate_laya_action_proposal(
    proposal: Any, *, expected_request_id: Any, policy: Any
) -> bool:
    """Validate an exact, request-bound proposal without dispatching it."""
    if not isinstance(proposal, dict) or not isinstance(policy, dict):
        return False
    if policy.get("enabled") is not True:
        return False
    allowed = policy.get("allowed_actions")
    if not isinstance(allowed, list) or "set_lights" not in allowed:
        return False
    if not isinstance(expected_request_id, str) or not expected_request_id.strip():
        return False
    if set(proposal) != {"schema_version", "tool_name", "arguments", "confidence", "request_id"}:
        return False
    if type(proposal.get("schema_version")) is not int or proposal["schema_version"] != 1:
        return False
    if proposal.get("tool_name") != "set_lights":
        return False
    if proposal.get("request_id") != expected_request_id:
        return False
    arguments = proposal.get("arguments")
    if not isinstance(arguments, dict) or set(arguments) != {"color", "effect"}:
        return False
    if arguments["color"] not in LIGHT_COLORS or arguments["effect"] not in LIGHT_EFFECTS:
        return False
    threshold = _confidence(policy.get("confidence_threshold"))
    confidence = _confidence(proposal.get("confidence"))
    return threshold is not None and confidence is not None and confidence >= threshold


def _confidence(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        return None
    return score


__all__ = [
    "LIGHT_COLORS",
    "LIGHT_EFFECTS",
    "bind_laya_action_proposal",
    "build_laya_action_proposal",
    "get_laya_action_questions",
    "validate_laya_action_proposal",
]
