"""Failure classification and context-aware recovery decisions."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .schemas import FailureClass, RecoveryDecision


_PATTERNS = (
    (FailureClass.PERMISSION, re.compile(r"permission|forbidden|unauthorized|owner.?lock|denied", re.I)),
    (FailureClass.VALIDATION, re.compile(r"validation|invalid|schema|malformed|bad request", re.I)),
    (FailureClass.RATE_LIMIT, re.compile(r"rate.?limit|too many requests|429", re.I)),
    (FailureClass.TOOL_UNAVAILABLE, re.compile(r"not found|unavailable|resource busy|camera_unavailable|vision.?busy|offline", re.I)),
    (FailureClass.UNSAFE_ACTION, re.compile(r"unsafe|quiet_hours|blocked|safety", re.I)),
    (FailureClass.BUDGET_EXCEEDED, re.compile(r"budget|max_iterations|max_tool_calls|max_retries", re.I)),
    (FailureClass.TEMPORARY, re.compile(r"timeout|temporar|retry|connection|network|503|502", re.I)),
)


class FailureClassifier:
    """Map tool/runtime errors into FailureClass without LLM involvement."""

    def classify(
        self,
        *,
        success: bool,
        result: Any = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FailureClass:
        if success:
            return FailureClass.NONE
        meta = metadata or {}
        explicit = meta.get("failure_class") or meta.get("error_code")
        if explicit:
            try:
                return FailureClass(str(explicit))
            except ValueError:
                pass
        text = " ".join(
            str(part)
            for part in (error, result, meta.get("error"), meta.get("reason"))
            if part
        )
        if not text.strip():
            return FailureClass.UNKNOWN
        for failure_class, pattern in _PATTERNS:
            if pattern.search(text):
                return failure_class
        if str(result).strip().lower().startswith("error"):
            return FailureClass.TEMPORARY
        return FailureClass.UNKNOWN


class RecoveryManager:
    """Deterministic recovery policy keyed by failure class."""

    def decide(
        self,
        failure_class: FailureClass,
        *,
        attempt: int = 0,
        max_retries: int = 2,
        alternate_tools: Optional[list] = None,
        has_plan: bool = True,
    ) -> RecoveryDecision:
        alts = [str(t) for t in (alternate_tools or []) if str(t)]
        if failure_class == FailureClass.NONE:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="continue",
                reason="no_failure",
            )
        if failure_class == FailureClass.TEMPORARY and attempt < max_retries:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="retry",
                should_retry=True,
                reason="transient_failure_retry",
            )
        if failure_class == FailureClass.TOOL_UNAVAILABLE and alts:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="switch_tool",
                should_switch_tool=True,
                alternate_tool=alts[0],
                reason="tool_unavailable_switch",
            )
        if failure_class in {FailureClass.INSUFFICIENT_CONTEXT, FailureClass.UNEXPECTED_RESULT}:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="gather_context_or_replan",
                should_replan=has_plan,
                should_ask_user=not has_plan,
                reason="need_more_context",
            )
        if failure_class == FailureClass.INVALID_PLAN:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="replan",
                should_replan=True,
                reason="plan_invalid",
            )
        if failure_class in {FailureClass.PERMISSION, FailureClass.UNSAFE_ACTION}:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="request_permission_or_abort",
                should_ask_user=True,
                should_abort=failure_class == FailureClass.UNSAFE_ACTION,
                reason="policy_blocked",
            )
        if failure_class in {FailureClass.PERMANENT, FailureClass.BUDGET_EXCEEDED, FailureClass.NO_PROGRESS}:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="abort",
                should_abort=True,
                reason="unrecoverable_or_budget",
            )
        if failure_class == FailureClass.VALIDATION:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="replan" if has_plan else "abort",
                should_replan=has_plan,
                should_abort=not has_plan,
                reason="validation_failed",
            )
        if alts:
            return RecoveryDecision(
                failure_class=failure_class,
                strategy="switch_tool",
                should_switch_tool=True,
                alternate_tool=alts[0],
                reason="unknown_try_alternate",
            )
        return RecoveryDecision(
            failure_class=failure_class,
            strategy="abort",
            should_abort=True,
            reason="no_recovery_path",
        )
