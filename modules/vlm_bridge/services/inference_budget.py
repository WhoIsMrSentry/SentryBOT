from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Callable, Dict, List, Mapping, Optional

VLM_INFERENCE_BUDGET_GATE_CONTRACT = True
VLM_INFERENCE_BUDGET_GATE_ROLE = "pre_inference_rate_budget_and_circuit_gate"
VLM_INFERENCE_BUDGET_GATE_STATUS_ONLY_SAFE = True


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str
    remaining_requests: int
    remaining_cost_units: float
    retry_after_s: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining_requests": self.remaining_requests,
            "remaining_cost_units": round(float(self.remaining_cost_units), 3),
            "retry_after_s": round(float(self.retry_after_s), 3),
        }


@dataclass
class VLMInferenceBudgetGate:
    """Pure pre-inference budget gate.

    The gate does not capture frames, call a VLM, call Ollama, or perform
    network IO. It only answers whether a future inference request would be
    allowed under explicit runtime budget limits.
    """

    enabled: bool = False
    max_requests_per_minute: int = 2
    max_cost_units_per_minute: float = 4.0
    min_interval_s: float = 5.0
    max_consecutive_failures: int = 2
    now_fn: Callable[[], float] = time
    _events: List[Dict[str, float]] = field(default_factory=list)
    _last_reserved_at: Optional[float] = None
    _consecutive_failures: int = 0

    @classmethod
    def from_config(cls, config: Optional[Mapping[str, Any]] = None) -> "VLMInferenceBudgetGate":
        cfg = dict(config or {})
        return cls(
            enabled=bool(cfg.get("enabled", False)),
            max_requests_per_minute=max(0, int(cfg.get("max_requests_per_minute", 2))),
            max_cost_units_per_minute=max(0.0, float(cfg.get("max_cost_units_per_minute", 4.0))),
            min_interval_s=max(0.0, float(cfg.get("min_interval_s", 5.0))),
            max_consecutive_failures=max(0, int(cfg.get("max_consecutive_failures", 2))),
        )

    def check(self, *, cost_units: float = 1.0, now: Optional[float] = None) -> BudgetDecision:
        current = float(self.now_fn() if now is None else now)
        cost = max(0.0, float(cost_units))
        self._prune(current)

        if not self.enabled:
            return BudgetDecision(False, "disabled", 0, 0.0)

        if self.max_consecutive_failures > 0 and self._consecutive_failures >= self.max_consecutive_failures:
            return BudgetDecision(False, "circuit_open_after_failures", 0, 0.0)

        if self._last_reserved_at is not None:
            elapsed = current - self._last_reserved_at
            if elapsed < self.min_interval_s:
                return BudgetDecision(
                    False,
                    "cooldown",
                    self._remaining_requests(),
                    self._remaining_cost_units(),
                    retry_after_s=self.min_interval_s - elapsed,
                )

        if self._remaining_requests() <= 0:
            return BudgetDecision(False, "request_budget_exhausted", 0, self._remaining_cost_units())

        if self._remaining_cost_units() < cost:
            return BudgetDecision(False, "cost_budget_exhausted", self._remaining_requests(), self._remaining_cost_units())

        return BudgetDecision(True, "allowed", self._remaining_requests() - 1, self._remaining_cost_units() - cost)

    def reserve(self, *, cost_units: float = 1.0, now: Optional[float] = None) -> BudgetDecision:
        current = float(self.now_fn() if now is None else now)
        decision = self.check(cost_units=cost_units, now=current)
        if decision.allowed:
            cost = max(0.0, float(cost_units))
            self._events.append({"t": current, "cost": cost})
            self._last_reserved_at = current
        return decision

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def status(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        current = float(self.now_fn() if now is None else now)
        self._prune(current)
        return {
            "enabled": self.enabled,
            "remaining_requests": self._remaining_requests(),
            "remaining_cost_units": round(self._remaining_cost_units(), 3),
            "min_interval_s": self.min_interval_s,
            "max_consecutive_failures": self.max_consecutive_failures,
            "consecutive_failures": self._consecutive_failures,
            "last_reserved_at": self._last_reserved_at,
            "status_only_safe": True,
            "activation_started": False,
        }

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        self._events = [event for event in self._events if event["t"] >= cutoff]

    def _remaining_requests(self) -> int:
        return max(0, int(self.max_requests_per_minute) - len(self._events))

    def _remaining_cost_units(self) -> float:
        spent = sum(float(event["cost"]) for event in self._events)
        return max(0.0, float(self.max_cost_units_per_minute) - spent)


def build_vlm_inference_budget_gate(config: Optional[Mapping[str, Any]] = None) -> VLMInferenceBudgetGate:
    return VLMInferenceBudgetGate.from_config(config)
