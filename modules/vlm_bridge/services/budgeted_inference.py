from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from modules.vlm_bridge.services.inference_budget import (
    BudgetDecision,
    VLMInferenceBudgetGate,
    build_vlm_inference_budget_gate,
)

VLM_BUDGET_GATE_INTEGRATION_CONTRACT = True
VLM_BUDGET_GATE_INTEGRATION_ROLE = "budget_gate_required_before_vlm_callable"
VLM_BUDGET_GATE_INTEGRATION_DEFAULT_NO_INFERENCE = True


@dataclass(frozen=True)
class BudgetedVLMResult:
    allowed: bool
    reason: str
    budget: Dict[str, Any]
    result: Optional[Any] = None
    inference_called: bool = False
    activation_started: bool = False
    camera_started: bool = False
    frame_captured: bool = False
    hardware_enabled: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "budget": dict(self.budget),
            "result": self.result,
            "inference_called": self.inference_called,
            "activation_started": self.activation_started,
            "camera_started": self.camera_started,
            "frame_captured": self.frame_captured,
            "hardware_enabled": self.hardware_enabled,
        }


class BudgetedVLMExecutor:
    """Require the VLM budget gate before an injected inference callable.

    This adapter does not own camera capture, frame acquisition, Ollama, network
    calls, or hardware. The actual inference function must be injected by a
    future runtime layer. When the gate denies, the callable is not invoked.
    """

    def __init__(
        self,
        *,
        gate: Optional[VLMInferenceBudgetGate] = None,
        inference_callable: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    ) -> None:
        self.gate = gate if gate is not None else build_vlm_inference_budget_gate()
        self.inference_callable = inference_callable

    def run(
        self,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        cost_units: float = 1.0,
        now: Optional[float] = None,
    ) -> BudgetedVLMResult:
        data = dict(payload or {})
        decision: BudgetDecision = self.gate.reserve(cost_units=cost_units, now=now)

        if not decision.allowed:
            return BudgetedVLMResult(
                allowed=False,
                reason=decision.reason,
                budget=decision.as_dict(),
                result=None,
                inference_called=False,
            )

        if self.inference_callable is None:
            return BudgetedVLMResult(
                allowed=False,
                reason="inference_callable_missing",
                budget=decision.as_dict(),
                result=None,
                inference_called=False,
            )

        try:
            result = self.inference_callable(data)
        except Exception as exc:
            self.gate.record_failure()
            return BudgetedVLMResult(
                allowed=False,
                reason="inference_callable_error",
                budget=decision.as_dict(),
                result={"error": f"{type(exc).__name__}: {exc}"},
                inference_called=True,
            )

        self.gate.record_success()
        return BudgetedVLMResult(
            allowed=True,
            reason="inference_completed",
            budget=decision.as_dict(),
            result=result,
            inference_called=True,
        )


def build_budgeted_vlm_executor(
    *,
    budget_config: Optional[Mapping[str, Any]] = None,
    inference_callable: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> BudgetedVLMExecutor:
    return BudgetedVLMExecutor(
        gate=build_vlm_inference_budget_gate(budget_config),
        inference_callable=inference_callable,
    )
