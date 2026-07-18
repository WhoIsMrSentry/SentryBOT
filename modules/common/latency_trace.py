from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Dict, Optional


class LatencyTraceStore:
    def __init__(self, max_traces: int = 200) -> None:
        self.max_traces = max(20, int(max_traces))
        self._lock = threading.RLock()
        self._traces: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._latest_id = ""

    def ensure(self, trace_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        key = str(trace_id or "").strip() or uuid.uuid4().hex[:16]
        now_wall = time.time()
        now_mono = time.monotonic()
        with self._lock:
            trace = self._traces.get(key)
            if trace is None:
                trace = {
                    "trace_id": key,
                    "created_at": now_wall,
                    "started_mono": now_mono,
                    "finished_at": None,
                    "status": "running",
                    "metadata": {},
                    "events": [],
                }
                self._traces[key] = trace
            if isinstance(metadata, dict):
                trace["metadata"].update(metadata)
            self._latest_id = key
            self._traces.move_to_end(key)
            self._trim_locked()
        return key

    def mark(self, trace_id: Optional[str], event: str, data: Optional[Dict[str, Any]] = None) -> str:
        key = self.ensure(trace_id)
        now_wall = time.time()
        now_mono = time.monotonic()
        with self._lock:
            trace = self._traces[key]
            trace["events"].append(
                {
                    "event": str(event),
                    "at": now_wall,
                    "elapsed_ms": round((now_mono - float(trace["started_mono"])) * 1000.0, 2),
                    "data": dict(data or {}),
                }
            )
            self._latest_id = key
            self._traces.move_to_end(key)
        return key

    def finish(self, trace_id: Optional[str], status: str = "done", data: Optional[Dict[str, Any]] = None) -> str:
        key = self.mark(trace_id, "trace.finished", {"status": status, **dict(data or {})})
        with self._lock:
            trace = self._traces[key]
            trace["finished_at"] = time.time()
            trace["status"] = str(status or "done")
        return key

    def get(self, trace_id: str) -> Optional[Dict[str, Any]]:
        key = str(trace_id or "").strip()
        with self._lock:
            trace = self._traces.get(key)
            return self._snapshot_locked(trace) if trace else None

    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            trace = self._traces.get(self._latest_id)
            return self._snapshot_locked(trace) if trace else None

    def _snapshot_locked(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        result = deepcopy(trace)
        result.pop("started_mono", None)
        events = result.get("events", [])
        if events:
            result["elapsed_ms"] = events[-1].get("elapsed_ms", 0.0)
        else:
            result["elapsed_ms"] = 0.0
        return result

    def _trim_locked(self) -> None:
        while len(self._traces) > self.max_traces:
            self._traces.popitem(last=False)


latency_trace = LatencyTraceStore()

__all__ = ["LatencyTraceStore", "latency_trace"]
