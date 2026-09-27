"""Safety tests for converting Laya's typed choices into inert proposals."""

import pytest

from modules.agent_core.services.laya_action_contract import (
    LIGHT_COLORS,
    LIGHT_EFFECTS,
    bind_laya_action_proposal,
    build_laya_action_proposal,
    get_laya_action_questions,
    validate_laya_action_proposal,
)
from modules.agent_core.services.laya_engine import LayaEngine


POLICY = {
    "enabled": True,
    "confidence_threshold": 0.85,
    "allowed_actions": ["set_lights"],
    "default_light_effect": "BREATHE",
}
ANSWERS = {
    "action_color": {"type": "choice", "choice": "blue", "confidence": 0.96},
    "action_effect": {"type": "choice", "choice": "unspecified", "confidence": 0.91},
}


def _proposal(**overrides):
    values = {
        "target_module": "neopixel",
        "module_confidence": 0.95,
        "is_direct_command": True,
        "direct_confidence": 0.96,
        "answers": ANSWERS,
        "policy": POLICY,
    }
    values.update(overrides)
    return build_laya_action_proposal(**values)


def test_action_questions_are_only_finite_choice_fields():
    questions = get_laya_action_questions()

    assert set(questions) == {"action_color", "action_effect"}
    assert all(question["type"] == "choice" for question in questions.values())
    assert set(questions["action_color"]["criteria"]) == {*LIGHT_COLORS, "unspecified"}
    assert set(questions["action_effect"]["criteria"]) == {*LIGHT_EFFECTS, "unspecified"}


def test_valid_laya_light_choices_create_inert_typed_proposal():
    proposal = _proposal()

    assert proposal == {
        "schema_version": 1,
        "tool_name": "set_lights",
        "arguments": {"effect": "BREATHE", "color": "blue"},
        "confidence": 0.91,
    }


def test_proposal_binds_to_current_request_and_validates_without_dispatch():
    bound = bind_laya_action_proposal(_proposal(), "request-123")

    assert bound["request_id"] == "request-123"
    assert validate_laya_action_proposal(
        bound, expected_request_id="request-123", policy=POLICY
    )
    assert not validate_laya_action_proposal(
        bound, expected_request_id="request-456", policy=POLICY
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda proposal: proposal.update(extra="unexpected"),
        lambda proposal: proposal.update(schema_version=True),
        lambda proposal: proposal.update(confidence=0.84),
        lambda proposal: proposal["arguments"].update(color="ultraviolet"),
        lambda proposal: proposal["arguments"].update(arbitrary=1),
    ],
)
def test_request_bound_proposal_rejects_schema_and_policy_violations(mutation):
    proposal = bind_laya_action_proposal(_proposal(), "request-123")
    mutation(proposal)

    assert not validate_laya_action_proposal(
        proposal, expected_request_id="request-123", policy=POLICY
    )


def test_proposal_binding_rejects_missing_or_conflicting_request_ids():
    proposal = _proposal()

    assert bind_laya_action_proposal(proposal, "  ") is None
    assert bind_laya_action_proposal({**proposal, "request_id": "older"}, "current") is None


def test_proposal_validator_fails_closed_when_feature_or_action_is_unapproved():
    bound = bind_laya_action_proposal(_proposal(), "request-123")

    assert not validate_laya_action_proposal(
        bound, expected_request_id="request-123", policy={**POLICY, "enabled": False}
    )
    assert not validate_laya_action_proposal(
        bound, expected_request_id="request-123", policy={**POLICY, "allowed_actions": []}
    )
    assert not validate_laya_action_proposal(
        bound, expected_request_id="request-123", policy={**POLICY, "confidence_threshold": float("nan")}
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"policy": {**POLICY, "enabled": False}},
        {"policy": {**POLICY, "allowed_actions": []}},
        {"target_module": "arduino_serial"},
        {"is_direct_command": False},
        {"module_confidence": 0.84},
        {"direct_confidence": 0.84},
        {"answers": {**ANSWERS, "action_color": {"type": "choice", "choice": "unspecified", "confidence": 0.99}}},
        {"answers": {**ANSWERS, "action_color": {"type": "choice", "choice": "javascript", "confidence": 0.99}}},
        {"answers": {**ANSWERS, "action_effect": {"type": "choice", "choice": "DELETE_ALL", "confidence": 0.99}}},
        {"answers": {**ANSWERS, "action_color": {"type": "score", "choice": "blue", "confidence": 0.99}}},
        {"policy": {**POLICY, "default_light_effect": "MOVE_MOTOR"}},
    ],
)
def test_invalid_or_unapproved_action_proposals_fail_closed(overrides):
    assert _proposal(**overrides) is None


def test_invalid_confidence_values_fail_closed():
    bad_answers = {
        **ANSWERS,
        "action_color": {"type": "choice", "choice": "blue", "confidence": float("nan")},
    }
    assert _proposal(answers=bad_answers) is None
    assert _proposal(module_confidence=True) is None


def test_laya_engine_requests_action_choices_only_when_opted_in():
    answers = {
        "target_module": {"choice": "neopixel", "confidence": 0.95},
        "is_direct_command": {"choice": "direct_action", "confidence": 0.96},
        "affective_event": {"choice": "neutral", "confidence": 0.9},
        "urgency": {"score": 0.4, "confidence": 0.9},
        **ANSWERS,
    }
    engine = LayaEngine(laya_cfg={"action_proposals": POLICY})
    engine._agent = type("MockLaya", (), {
        "system_one": lambda _self, _state, questions: {
            "answers": answers,
            "question_ids": list(questions),
        },
    })()
    engine._is_available = True
    engine._load_attempted = True

    decision = engine.decide("Işıkları mavi yap")

    assert decision is not None
    assert decision.suggested_action == _proposal()


def test_action_proposal_feature_defaults_off():
    engine = LayaEngine()
    captured = {}

    class MockLaya:
        def system_one(self, _state, questions):
            captured.update(questions)
            return {"answers": {
                "target_module": {"choice": "neopixel", "confidence": 0.95},
                "is_direct_command": {"choice": "direct_action", "confidence": 0.96},
                "affective_event": {"choice": "neutral", "confidence": 0.9},
                "urgency": {"score": 0.4, "confidence": 0.9},
                **ANSWERS,
            }}

    engine._agent = MockLaya()
    engine._is_available = True
    engine._load_attempted = True
    decision = engine.decide("Işıkları mavi yap")

    assert decision is not None and decision.suggested_action is None
    assert "action_color" not in captured
    assert "action_effect" not in captured


def test_emergency_safety_bypass_defaults_off():
    assert LayaEngine().emergency_bypass_safety is False
