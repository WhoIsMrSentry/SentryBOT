from __future__ import annotations

import json
from pathlib import Path

from modules.autonomy.services.pet_companion_core import (
    PET_COMPANION_CORE_CONTRACT,
    PET_COMPANION_CORE_HARDWARE_SAFE,
    PET_COMPANION_CORE_ROLE,
    DEFAULT_PROFILE,
    PetCompanionCore,
    PersonalityProfile,
    decide_pet_companion_behavior,
    load_personality_profile,
)


def test_pet_companion_core_contract_markers():
    assert PET_COMPANION_CORE_CONTRACT is True
    assert PET_COMPANION_CORE_ROLE == "personality_bond_routine_to_semantic_pet_behavior"
    assert PET_COMPANION_CORE_HARDWARE_SAFE is True


def test_owner_presence_and_bond_produces_attend_owner_intent():
    core = PetCompanionCore()
    decision = core.decide(
        {
            "needs": {"social": 0.7, "curiosity": 0.1, "boredom": 0.1, "safety": 0.0},
            "bond": {"trust": 0.8, "affection": 0.9},
            "routine": {"energy": 0.8},
            "perception": {"owner_present": True},
        }
    ).as_dict()

    assert decision["intent"] == "attend_owner"
    assert "orient_to_owner" in decision["goal_hints"]
    assert decision["safety"]["hardware_enabled"] is False
    assert decision["status_only"] is True


def test_safety_need_overrides_pet_curiosity():
    core = PetCompanionCore()
    decision = core.decide(
        {
            "needs": {"safety": 0.8, "curiosity": 1.0, "boredom": 1.0, "social": 0.9},
            "routine": {"energy": 1.0},
            "perception": {"owner_present": True},
        }
    ).as_dict()

    assert decision["intent"] == "safe_observe"
    assert "avoid_motion_until_clear" in decision["goal_hints"]
    assert decision["safety"]["motion_started"] is False


def test_low_energy_produces_rest_nearby_intent():
    core = PetCompanionCore()
    decision = core.decide(
        {
            "needs": {"social": 0.4, "curiosity": 0.4, "boredom": 0.4, "safety": 0.0},
            "routine": {"energy": 0.1},
            "perception": {"owner_present": True},
        }
    ).as_dict()

    assert decision["intent"] == "rest_nearby"
    assert "rest" in decision["goal_hints"]
    assert decision["needs_bias"]["energy_recovery"] == 0.5


def test_curiosity_or_boredom_produces_alive_behavior():
    profile = PersonalityProfile.from_mapping(
        {
            **DEFAULT_PROFILE,
            "traits": {**DEFAULT_PROFILE["traits"], "sociability": 0.2, "curiosity": 1.0},
        }
    )
    core = PetCompanionCore(profile)
    decision = core.decide(
        {
            "needs": {"social": 0.0, "curiosity": 0.8, "boredom": 0.5, "safety": 0.0},
            "routine": {"energy": 0.9},
            "perception": {"owner_present": False},
        }
    ).as_dict()

    assert decision["intent"] in {"curious_inspect", "playful_ping"}
    assert decision["safety"]["camera_started"] is False
    assert decision["safety"]["vlm_started"] is False


def test_load_profile_from_config_file(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {
                "name": "testbot",
                "traits": {"curiosity": 0.1, "sociability": 0.9},
                "style": {"speech": "quiet", "motion": "slow", "expression": "soft"},
            }
        ),
        encoding="utf-8",
    )

    profile = load_personality_profile(path)
    assert profile.name == "testbot"
    assert profile.curiosity == 0.1
    assert profile.sociability == 0.9
    assert profile.speech_style == "quiet"


def test_public_decide_helper_returns_semantic_safe_decision():
    decision = decide_pet_companion_behavior(
        {
            "needs": {"social": 0.6},
            "bond": {"trust": 0.6, "affection": 0.6},
            "routine": {"energy": 0.7},
            "perception": {"owner_present": True},
        }
    )

    assert isinstance(decision["intent"], str)
    assert decision["safety"]["hardware_enabled"] is False
    assert decision["safety"]["semantic_only"] is True
