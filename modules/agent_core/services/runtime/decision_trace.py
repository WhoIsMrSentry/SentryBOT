"""Safe, machine-readable decision traces (no chain-of-thought)."""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional

from .schemas import DecisionTrace

_SENSITIVE_META_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "messages",
        "token",
        "tokens",
        "api_key",
        "authorization",
        "password",
        "secret",
        "credentials",
        "raw_args",
        "arguments",
        "tool_args",
    }
)


class DecisionTraceStore:
    """Ring buffer of concise decision summaries for debugging and APIs."""

    def __init__(self, maxlen: int = 64) -> None:
        n = max(1, int(maxlen))
        self._traces: Deque[DecisionTrace] = deque(maxlen=n)
        self.maxlen = n

    def add(self, trace: DecisionTrace) -> DecisionTrace:
        self._traces.append(trace)
        return trace

    def record(
        self,
        *,
        goal_id: str,
        decision: str,
        reason: str,
        tool: Optional[str] = None,
        result_summary: str = "",
        next_action: str = "",
        evaluation: Optional[Dict] = None,
        iteration: int = 0,
        metadata: Optional[Dict] = None,
    ) -> DecisionTrace:
        trace = DecisionTrace(
            goal_id=goal_id,
            decision=decision,
            reason=reason,
            tool=tool,
            result_summary=_truncate(result_summary),
            next_action=next_action,
            evaluation=evaluation,
            iteration=iteration,
            metadata=_sanitize_metadata(metadata or {}),
        )
        return self.add(trace)

    def recent(self, limit: int = 20) -> List[Dict]:
        items = list(self._traces)[-max(1, int(limit)) :]
        return [t.to_dict() for t in items]

    def query(
        self,
        *,
        limit: int = 20,
        goal_id: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        items = list(self._traces)
        if goal_id:
            gid = str(goal_id)
            items = [t for t in items if t.goal_id == gid]
        if since is not None:
            try:
                cutoff = float(since)
            except (TypeError, ValueError):
                cutoff = None
            if cutoff is not None:
                items = [t for t in items if float(t.timestamp) >= cutoff]
        items = items[-max(1, int(limit)) :]
        return [to_public_trace(t) for t in items]

    def clear(self) -> None:
        self._traces.clear()

    def __len__(self) -> int:
        return len(self._traces)

    def __bool__(self) -> bool:
        # Empty stores are still valid injected dependencies.
        return True


def to_public_trace(trace: DecisionTrace) -> Dict[str, Any]:
    """API DTO — no prompts, secrets, or raw tool arguments."""
    evaluation = trace.evaluation if isinstance(trace.evaluation, dict) else {}
    meta = _sanitize_metadata(trace.metadata or {})
    outcome = "success"
    if evaluation.get("execution_success") is False:
        outcome = "failure"
    elif str(trace.decision).endswith("failed") or trace.decision == "stop":
        outcome = "failure"
    elif trace.decision in {"abort", "tool_failed"}:
        outcome = "failure"

    recovery = meta.get("recovery")
    return {
        "trace_id": trace.id,
        "goal_id": trace.goal_id,
        "decision": trace.decision,
        "action": trace.decision,
        "capability": meta.get("capability"),
        "tool": trace.tool,
        "reason": _truncate(trace.reason, 200),
        "result_summary": _truncate(trace.result_summary, 200),
        "outcome": outcome,
        "recovery": recovery if isinstance(recovery, dict) else None,
        "next_action": trace.next_action,
        "evaluation": {
            "execution_success": evaluation.get("execution_success"),
            "failure_class": evaluation.get("failure_class"),
        }
        if evaluation
        else None,
        "iteration": trace.iteration,
        "timestamp": trace.timestamp,
    }


def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        low = str(key).lower()
        if low in _SENSITIVE_META_KEYS or any(s in low for s in ("prompt", "secret", "token", "password")):
            continue
        if isinstance(value, dict):
            out[str(key)] = _sanitize_metadata(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value if not isinstance(value, str) else _truncate(value, 200)
        elif isinstance(value, list):
            out[str(key)] = [str(item)[:80] for item in value[:8]]
    return out


def _truncate(text: str, limit: int = 240) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
