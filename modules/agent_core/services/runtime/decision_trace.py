"""Safe, machine-readable decision traces with lock protection and rotating JSONL export."""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import threading
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
    """Thread-safe ring buffer of concise decision summaries with optional rotating JSONL log."""

    def __init__(
        self,
        maxlen: int = 64,
        *,
        log_path: Optional[str | Path] = None,
        max_bytes: int = 262_144,
        backup_count: int = 2,
    ) -> None:
        n = max(1, int(maxlen))
        self._lock = threading.Lock()
        self._traces: Deque[DecisionTrace] = deque(maxlen=n)
        self.maxlen = n
        self._log_path: Optional[Path] = Path(str(log_path).strip()) if str(log_path or "").strip() else None
        self._max_bytes = max(1024, int(max_bytes))
        self._backup_count = max(0, int(backup_count))

    def _rotate_if_needed(self) -> None:
        if self._log_path is None or not self._log_path.exists():
            return
        try:
            if self._log_path.stat().st_size < self._max_bytes:
                return
        except OSError:
            return
        if self._backup_count <= 0:
            try:
                self._log_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        for idx in range(self._backup_count, 0, -1):
            src = self._log_path if idx == 1 else self._log_path.with_name(f"{self._log_path.name}.{idx - 1}")
            dst = self._log_path.with_name(f"{self._log_path.name}.{idx}")
            if src.exists():
                try:
                    if dst.exists():
                        dst.unlink()
                    src.replace(dst)
                except OSError:
                    pass

    def _write_jsonl(self, trace: DecisionTrace) -> None:
        if self._log_path is None:
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            line = json.dumps(to_public_trace(trace), ensure_ascii=False, default=str)
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def add(self, trace: DecisionTrace) -> DecisionTrace:
        with self._lock:
            self._traces.append(trace)
            self._write_jsonl(trace)
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
        with self._lock:
            items = list(self._traces)[-max(1, int(limit)) :]
        return [t.to_dict() for t in items]

    def latest_replan(self) -> Optional[Dict[str, Any]]:
        """Return the most recent replan trace DTO without mutating buffer state."""
        with self._lock:
            snapshot = list(self._traces)
        for trace in reversed(snapshot):
            if trace.decision in {"contextual_replan", "replan"} or trace.next_action == "replan":
                return to_public_trace(trace)
        return None

    def query(
        self,
        *,
        limit: int = 20,
        goal_id: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
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
        with self._lock:
            self._traces.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)

    def __bool__(self) -> bool:
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


__all__ = ["DecisionTraceStore", "to_public_trace"]
