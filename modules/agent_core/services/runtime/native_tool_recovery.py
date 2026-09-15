"""Bounded tool failure handling for the native history loop."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .capability_index import CapabilityIndex
from .decision_trace import DecisionTraceStore
from .progress_tracker import ProgressTracker
from .recovery import FailureClassifier, RecoveryManager
from .schemas import FailureClass


# Tools safe to auto-retry / auto-substitute without duplicating side effects.
READ_ONLY_TOOLS = frozenset(
    {
        "get_vision",
        "get_visual_context",
        "describe_scene",
        "ask_vlm_about_scene",
        "get_sensor_data",
        "get_location",
        "list_locations",
        "pathfind",
        "search_memory",
        "search_social_memory",
        "get_action_status",
        "get_last_rfid",
    }
)


def looks_like_tool_error(result: Any) -> bool:
    text = str(result or "").strip().lower()
    if not text:
        return False
    return (
        text.startswith("error")
        or "error executing" in text
        or text.startswith("traceback")
        or text.startswith("görüş verisi şu an kullanılamıyor")
    )


def format_tool_content(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


class NativeToolRecovery:
    """Classify tool failures, decide recovery, optionally retry read-only tools."""

    def __init__(
        self,
        *,
        classifier: Optional[FailureClassifier] = None,
        recovery: Optional[RecoveryManager] = None,
        capabilities: Optional[CapabilityIndex] = None,
        progress: Optional[ProgressTracker] = None,
        traces: Optional[DecisionTraceStore] = None,
        max_retries: int = 1,
        goal_id: str = "native_turn",
    ) -> None:
        self.classifier = classifier or FailureClassifier()
        self.recovery = recovery or RecoveryManager()
        self.capabilities = capabilities or CapabilityIndex.from_robot_registry()
        self.progress = progress or ProgressTracker(max_identical=3, max_zero_progress=3)
        self.traces = traces
        self.max_retries = max(0, int(max_retries))
        self.goal_id = goal_id
        self._retry_counts: Dict[str, int] = {}
        self.stop_reason: str = ""

    def handle(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        *,
        execute_fn,
        available_tools: Optional[Sequence[str]] = None,
        iteration: int = 0,
    ) -> Tuple[Any, Dict[str, Any], bool]:
        """Return (result_for_history, meta, should_stop_loop)."""
        success = not looks_like_tool_error(result)
        failure = self.classifier.classify(success=success, result=result)
        signature = f"{tool_name}:{sorted((args or {}).items())}"
        stall = self.progress.record(signature, progressed=success)
        if stall:
            self.stop_reason = stall
            meta = self._meta(tool_name, success, failure, None, result, stopped=stall)
            self._trace(tool_name, failure, meta, iteration=iteration, next_action="stop")
            return self._wrap(result, meta), meta, True

        if success:
            meta = self._meta(tool_name, True, FailureClass.NONE, None, result)
            self._trace(tool_name, FailureClass.NONE, meta, iteration=iteration, next_action="continue")
            return result, meta, False

        caps = self.capabilities.capabilities_for_tool(tool_name)
        alts: List[str] = []
        for cap in caps:
            for candidate in self.capabilities.tools_for_capability(cap):
                if candidate == tool_name:
                    continue
                if available_tools is not None and candidate not in available_tools:
                    continue
                if candidate not in alts:
                    alts.append(candidate)

        attempt = int(self._retry_counts.get(tool_name, 0))
        decision = self.recovery.decide(
            failure,
            attempt=attempt,
            max_retries=self.max_retries,
            alternate_tools=alts,
            has_plan=False,
        )

        # Bounded auto-retry only for read-only tools.
        if (
            decision.should_retry
            and tool_name in READ_ONLY_TOOLS
            and attempt < self.max_retries
        ):
            self._retry_counts[tool_name] = attempt + 1
            retry_result = execute_fn(tool_name, dict(args or {}))
            retry_success = not looks_like_tool_error(retry_result)
            retry_failure = self.classifier.classify(success=retry_success, result=retry_result)
            meta = self._meta(
                tool_name,
                retry_success,
                retry_failure if not retry_success else FailureClass.NONE,
                decision,
                retry_result,
                recovered_via="retry",
            )
            self.progress.record(signature + ":retry", progressed=retry_success)
            self._trace(
                tool_name,
                retry_failure if not retry_success else FailureClass.NONE,
                meta,
                iteration=iteration,
                next_action="continue" if retry_success else decision.strategy,
            )
            if retry_success:
                return self._wrap(retry_result, meta), meta, False
            result = retry_result
            failure = retry_failure

        # Bounded alternate tool only for read-only tools.
        if (
            decision.should_switch_tool
            and decision.alternate_tool
            and decision.alternate_tool in READ_ONLY_TOOLS
            and (available_tools is None or decision.alternate_tool in set(available_tools))
        ):
            alt = decision.alternate_tool
            alt_result = execute_fn(alt, dict(args or {}))
            alt_success = not looks_like_tool_error(alt_result)
            alt_failure = self.classifier.classify(success=alt_success, result=alt_result)
            meta = self._meta(
                tool_name,
                alt_success,
                alt_failure if not alt_success else FailureClass.NONE,
                decision,
                alt_result,
                recovered_via="switch_tool",
                alternate_tool=alt,
            )
            self.progress.record(f"{alt}:alt", progressed=alt_success)
            self._trace(
                alt,
                alt_failure if not alt_success else FailureClass.NONE,
                meta,
                iteration=iteration,
                next_action="continue" if alt_success else "abort",
            )
            wrapped = self._wrap(alt_result, meta)
            if decision.should_abort and not alt_success:
                self.stop_reason = decision.reason or "abort"
                return wrapped, meta, True
            return wrapped, meta, False

        meta = self._meta(tool_name, False, failure, decision, result)
        stop = bool(decision.should_abort)
        if stop:
            self.stop_reason = decision.reason or "abort"
        self._trace(
            tool_name,
            failure,
            meta,
            iteration=iteration,
            next_action=decision.strategy,
        )
        return self._wrap(result, meta), meta, stop

    def _meta(
        self,
        tool_name: str,
        success: bool,
        failure: FailureClass,
        decision: Any,
        result: Any,
        *,
        recovered_via: Optional[str] = None,
        alternate_tool: Optional[str] = None,
        stopped: Optional[str] = None,
    ) -> Dict[str, Any]:
        recovery_payload = None
        if decision is not None:
            recovery_payload = {
                "suggested_action": decision.strategy,
                "reason": decision.reason,
                "should_retry": bool(decision.should_retry),
                "should_switch_tool": bool(decision.should_switch_tool),
                "should_ask_user": bool(decision.should_ask_user),
                "should_abort": bool(decision.should_abort),
                "alternate_tool": decision.alternate_tool,
                "recovered_via": recovered_via,
            }
        return {
            "success": bool(success),
            "tool": tool_name,
            "failure": {
                "type": failure.value,
                "recoverable": failure
                not in {
                    FailureClass.PERMANENT,
                    FailureClass.UNSAFE_ACTION,
                    FailureClass.BUDGET_EXCEEDED,
                    FailureClass.NO_PROGRESS,
                    FailureClass.NONE,
                }
                and not success,
            },
            "recovery": recovery_payload,
            "alternate_tool": alternate_tool,
            "stopped": stopped,
            "result_preview": str(result)[:200],
        }

    def _wrap(self, result: Any, meta: Dict[str, Any]) -> Any:
        # Additive envelope: preserve string results for simple consumers via "raw"
        # while exposing structured recovery for the LLM / tracers.
        if isinstance(result, dict) and "success" in result and "recovery" in result:
            out = dict(result)
            out.setdefault("failure", meta.get("failure"))
            out["recovery"] = meta.get("recovery")
            return out
        return {
            "success": bool(meta.get("success")),
            "raw": result,
            "failure": meta.get("failure"),
            "recovery": meta.get("recovery"),
        }

    def _trace(
        self,
        tool_name: str,
        failure: FailureClass,
        meta: Dict[str, Any],
        *,
        iteration: int,
        next_action: str,
    ) -> None:
        if self.traces is None:
            return
        self.traces.record(
            goal_id=self.goal_id,
            decision="use_tool" if meta.get("success") else "tool_failed",
            reason=str((meta.get("recovery") or {}).get("reason") or failure.value or "ok"),
            tool=tool_name,
            result_summary=str(meta.get("result_preview") or ""),
            next_action=next_action,
            evaluation={
                "execution_success": bool(meta.get("success")),
                "failure_class": failure.value,
            },
            iteration=iteration,
            metadata={
                "recovery": meta.get("recovery"),
                "capability": (self.capabilities.capabilities_for_tool(tool_name) or [None])[0],
            },
        )
