from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

VISION_CONTEXT_BRIDGE_CONTRACT = True
VISION_CONTEXT_BRIDGE_ROLE = "camera_vlm_to_autonomy_semantic_context_adapter"
VISION_CONTEXT_BRIDGE_STATUS_ONLY = True


def _now() -> float:
    return float(time())


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _compact_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def _compact_list(value: Any, limit: int = 8) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [_compact_text(value)]
    if isinstance(value, Sequence):
        return list(value[:limit])
    return [value]


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "running", "ready", "ok"}
    return bool(value)


@dataclass
class VisionContextBridge:
    """Status-only bridge from camera/VLM facts into autonomy semantic context.

    This class never opens a camera, never captures a frame, never calls a VLM,
    and never calls Ollama. It only normalizes already-produced status/result
    dictionaries so autonomy can consume them safely.
    """

    config: Optional[Mapping[str, Any]] = None
    history_limit: int = 20
    _history: List[Dict[str, Any]] = field(default_factory=list)

    def ingest_camera_status(
        self,
        status: Optional[Mapping[str, Any]],
        *,
        source: str = "camera",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        data = _as_mapping(status)
        context = {
            "kind": "camera_status",
            "source": source,
            "timestamp": float(_now() if now is None else now),
            "enabled": _truthy(data.get("enabled", data.get("camera_enabled", False))),
            "running": _truthy(data.get("running", data.get("active", False))),
            "has_frame": _truthy(data.get("has_frame", data.get("frame_available", False))),
            "degraded": _truthy(data.get("degraded", data.get("gave_up", False))),
            "reason": _compact_text(data.get("reason", data.get("status", "")), limit=160),
        }
        return self._remember(context)

    def ingest_vlm_result(
        self,
        result: Optional[Mapping[str, Any]],
        *,
        source: str = "vlm",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        data = _as_mapping(result)
        context = {
            "kind": "vlm_semantic_context",
            "source": source,
            "timestamp": float(_now() if now is None else now),
            "caption": _compact_text(data.get("caption", data.get("description", ""))),
            "objects": _compact_list(data.get("objects", data.get("labels", []))),
            "people": _compact_list(data.get("people", data.get("persons", []))),
            "scene": _compact_text(data.get("scene", data.get("place", "")), limit=120),
            "risk": _compact_text(data.get("risk", data.get("safety", "")), limit=80),
            "confidence": data.get("confidence"),
        }
        return self._remember(context)

    def build_context(
        self,
        *,
        camera_status: Optional[Mapping[str, Any]] = None,
        vlm_result: Optional[Mapping[str, Any]] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        if camera_status is not None:
            entries.append(self.ingest_camera_status(camera_status, now=now))
        if vlm_result is not None:
            entries.append(self.ingest_vlm_result(vlm_result, now=now))
        return {
            "kind": "vision_context_bundle",
            "timestamp": float(_now() if now is None else now),
            "entries": entries,
            "latest": self.latest(),
            "status_only": True,
            "activation_started": False,
        }

    def latest(self) -> Optional[Dict[str, Any]]:
        return dict(self._history[-1]) if self._history else None

    def history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit is None:
            return [dict(item) for item in self._history]
        return [dict(item) for item in self._history[-int(limit):]]

    def clear(self) -> None:
        self._history.clear()

    def _remember(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._history.append(dict(context))
        if len(self._history) > self.history_limit:
            self._history = self._history[-self.history_limit :]
        return dict(context)


def build_vision_context(
    *,
    camera_status: Optional[Mapping[str, Any]] = None,
    vlm_result: Optional[Mapping[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    return VisionContextBridge().build_context(
        camera_status=camera_status,
        vlm_result=vlm_result,
        now=now,
    )
