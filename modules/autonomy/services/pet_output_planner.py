from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

PET_OUTPUT_PLANNER_CONTRACT = True
PET_OUTPUT_PLANNER_ROLE = "pet_intent_to_expression_motion_speech_semantic_plan"
PET_OUTPUT_PLANNER_HARDWARE_SAFE = True


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class PetOutputPlan:
    intent: str
    expression: Dict[str, Any] = field(default_factory=dict)
    motion: Dict[str, Any] = field(default_factory=dict)
    speech: Dict[str, Any] = field(default_factory=dict)
    led: Dict[str, Any] = field(default_factory=dict)
    safety: Dict[str, bool] = field(default_factory=dict)
    semantic_only: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "expression": dict(self.expression),
            "motion": dict(self.motion),
            "speech": dict(self.speech),
            "led": dict(self.led),
            "safety": dict(self.safety),
            "semantic_only": self.semantic_only,
        }


class PetOutputPlanner:
    """Translate pet companion hints into semantic expression/motion/speech plan.

    This module does not execute OLED, servo, LED, TTS, audio, camera, or VLM.
    It only produces safe semantic commands that later execution layers can
    route through capability and hardware gates.
    """

    def plan(self, pet_companion: Optional[Mapping[str, Any]] = None) -> PetOutputPlan:
        data = _mapping(pet_companion)
        intent = _text(data.get("intent"), "calm_idle")
        expression_hint = _text(data.get("expression_hint"), self._default_expression(intent))
        motion_hint = _text(data.get("motion_hint"), self._default_motion(intent))
        speech_hint = _text(data.get("speech_hint"), self._default_speech(intent))

        intensity = self._intensity_for(intent)
        expression = {
            "type": "expression",
            "name": expression_hint,
            "intent": intent,
            "intensity": intensity,
            "duration_s": 2.0,
            "semantic_only": True,
            "hardware_started": False,
        }
        motion = {
            "type": "motion",
            "name": motion_hint,
            "intent": intent,
            "amplitude": self._motion_amplitude(intent),
            "duration_s": 1.5,
            "semantic_only": True,
            "hardware_started": False,
            "requires_arm_gate": True,
        }
        speech = {
            "type": "speech",
            "style": speech_hint,
            "intent": intent,
            "utterance": self._utterance_for(intent, speech_hint),
            "semantic_only": True,
            "tts_started": False,
        }
        led = {
            "type": "led",
            "pattern": self._led_pattern(intent),
            "intent": intent,
            "semantic_only": True,
            "hardware_started": False,
        }
        safety = {
            "camera_started": False,
            "frame_captured": False,
            "vlm_started": False,
            "tts_started": False,
            "audio_started": False,
            "motion_started": False,
            "led_started": False,
            "hardware_enabled": False,
            "semantic_only": True,
        }
        return PetOutputPlan(
            intent=intent,
            expression=expression,
            motion=motion,
            speech=speech,
            led=led,
            safety=safety,
            semantic_only=True,
        )

    def _default_expression(self, intent: str) -> str:
        return {
            "safe_observe": "alert_soft",
            "rest_nearby": "sleepy_calm",
            "attend_owner": "happy_attentive",
            "listen_owner": "listening",
            "curious_inspect": "curious",
            "playful_ping": "playful",
            "calm_idle": "calm_alive",
        }.get(intent, "calm_alive")

    def _default_motion(self, intent: str) -> str:
        return {
            "safe_observe": "freeze_or_slow_scan",
            "rest_nearby": "settle_near_owner",
            "attend_owner": "orient_to_owner",
            "listen_owner": "hold_still_attention",
            "curious_inspect": "small_head_tilt_or_scan",
            "playful_ping": "small_bouncy_idle",
            "calm_idle": "breathing_idle",
        }.get(intent, "breathing_idle")

    def _default_speech(self, intent: str) -> str:
        return {
            "safe_observe": "silent_or_short_check",
            "rest_nearby": "minimal",
            "attend_owner": "short_warm",
            "listen_owner": "do_not_interrupt",
            "curious_inspect": "curious_short",
            "playful_ping": "playful_short",
            "calm_idle": "silent",
        }.get(intent, "silent")

    def _intensity_for(self, intent: str) -> float:
        return {
            "safe_observe": 0.25,
            "rest_nearby": 0.18,
            "attend_owner": 0.55,
            "listen_owner": 0.35,
            "curious_inspect": 0.50,
            "playful_ping": 0.62,
            "calm_idle": 0.25,
        }.get(intent, 0.25)

    def _motion_amplitude(self, intent: str) -> float:
        return {
            "safe_observe": 0.05,
            "rest_nearby": 0.08,
            "attend_owner": 0.25,
            "listen_owner": 0.03,
            "curious_inspect": 0.22,
            "playful_ping": 0.32,
            "calm_idle": 0.10,
        }.get(intent, 0.10)

    def _led_pattern(self, intent: str) -> str:
        return {
            "safe_observe": "soft_alert",
            "rest_nearby": "dim_breath",
            "attend_owner": "warm_pulse",
            "listen_owner": "focus_dot",
            "curious_inspect": "curious_spark",
            "playful_ping": "playful_blink",
            "calm_idle": "slow_breath",
        }.get(intent, "slow_breath")

    def _utterance_for(self, intent: str, speech_hint: str) -> str:
        if speech_hint in {"silent", "minimal", "do_not_interrupt"}:
            return ""
        return {
            "attend_owner": "BuradayÄ±m.",
            "curious_inspect": "Bunu merak ettim.",
            "playful_ping": "Bir ÅŸey yapalÄ±m mÄ±?",
            "safe_observe": "Dikkat ediyorum.",
        }.get(intent, "")


def build_pet_output_plan(pet_companion: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return PetOutputPlanner().plan(pet_companion).as_dict()
