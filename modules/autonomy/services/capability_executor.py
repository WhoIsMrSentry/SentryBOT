from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class CapabilityExecutor:
    def __init__(self, client: Any, registry_path: Optional[Path] = None) -> None:
        self.client = client
        self.registry_path = registry_path or Path(__file__).resolve().parents[3] / "config" / "robot_capability_registry.json"
        self.registry = self._load_registry()
        self._last_result: Dict[str, Any] = {"ok": True, "reason": "never_executed"}

    def _load_registry(self) -> Dict[str, Any]:
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("capabilities"), dict):
            raise ValueError("robot capability registry is invalid")
        return data

    def status(self) -> Dict[str, Any]:
        capabilities = self.registry.get("capabilities", {})
        return {
            "ok": True,
            "registry_path": str(self.registry_path),
            "capability_count": len(capabilities),
            "capabilities": sorted(capabilities),
            "last_result": dict(self._last_result),
        }

    def execute(self, name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        started = time.monotonic()
        params = params if isinstance(params, dict) else {}
        capability = self.registry.get("capabilities", {}).get(name)
        if not isinstance(capability, dict):
            return self._remember(name, False, "capability_not_found", started)
        if not bool(capability.get("enabled", True)):
            return self._remember(name, False, "capability_disabled", started)
        risk = str(capability.get("risk") or "none").lower()
        blocked = {str(x).lower() for x in self.registry.get("policy", {}).get("blocked_risks", ["critical"])}
        if risk in blocked:
            return self._remember(name, False, f"risk_blocked:{risk}", started)

        handler = str(capability.get("handler") or "").strip()
        try:
            response = self._dispatch(handler, params, capability)
            ok = response is not None and not (isinstance(response, dict) and response.get("ok") is False)
            result = self._remember(name, ok, "executed" if ok else "handler_failed", started)
            result["handler"] = handler
            result["response"] = response
            return result
        except Exception as exc:
            result = self._remember(name, False, "handler_exception", started)
            result["handler"] = handler
            result["error"] = str(exc)
            return result

    def _dispatch(self, handler: str, params: Dict[str, Any], capability: Dict[str, Any]) -> Any:
        if handler == "expression_event":
            event = str(params.get("event") or params.get("type") or "needs.balance")
            data = params.get("data") if isinstance(params.get("data"), dict) else {}
            return self.client._post("expression", "/event", {"type": event, "data": data})
        if handler == "animate":
            name = str(params.get("name") or capability.get("default_name") or "idle")
            speed = float(params.get("speed", 1.0))
            return self.client._post("animate", "/run", params={"name": name, "speed": speed, "loop": False}, timeout_s=4.0)
        if handler == "stop_motion":
            animation = self.client._post("animate", "/stop", timeout_s=1.0)
            liveliness = self.client.set_liveliness(False)
            return {"ok": bool(animation is not None or liveliness is not None), "animation": animation, "liveliness": liveliness}
        if handler == "vision_latest":
            return self.client._get_vlm("/results/latest")
        if handler == "vision_refresh":
            reason = str(params.get("reason") or "companion_goal")
            return self.client._post("vlm", "/context/refresh", {"reason": reason, "mode": "semantic"}, timeout_s=8.0)
        if handler == "track_target":
            label = str(params.get("label") or "person").strip().lower()
            strategy = str(params.get("strategy") or "largest").strip().lower()
            track_id = params.get("track_id")
            selection = self.client._post(
                "camera",
                "/tracking/select",
                {"label": label, "strategy": strategy, "track_id": track_id},
                timeout_s=1.0,
            )
            follow = None
            if label == "person" and bool(params.get("follow", True)):
                person = str(params.get("person") or "").strip() or None
                follow = self.client._post("vlm", "/follow/start", params={"person": person} if person else None, timeout_s=1.0)
            return {"ok": selection is not None, "selection": selection, "follow": follow}
        if handler == "rest_corner":
            if hasattr(self.client, "execute_rest_corner"):
                return self.client.execute_rest_corner(params)
            return self.client._post("autonomy", "/navigation/rest-corner", json=params, timeout_s=1.5)
        if handler == "memory_observe":
            payload = dict(params)
            if "kind" not in payload:
                payload["kind"] = "episode"
            if "name" not in payload:
                payload["name"] = str(params.get("summary") or "companion_event")[:80]
            if hasattr(self.client, "world_memory_observe"):
                return self.client.world_memory_observe(payload)
            return self.client._post("autonomy", "/memory/observe", json=payload, timeout_s=1.0)
        if handler == "speak":
            text = str(params.get("text") or capability.get("fallback_text") or "").strip()
            if not text:
                return {"ok": True, "skipped": True, "reason": "empty_text"}
            return self.client.speak_preferred(text, tone=params.get("tone"), language=params.get("language"))
        # BEGIN BATCH04 CAPABILITY HANDLERS
        if handler == "navigation_goal":
            return self.client._post("autonomy", "/navigation/goal", json=params, timeout_s=2.0)
        if handler == "owner_learn":
            return self.client._post("autonomy", "/owner/learn", json=params, timeout_s=1.0)
        if handler == "owner_identify":
            return self.client._post("autonomy", "/owner/identify", json=params, timeout_s=1.0)
        if handler == "asset_status":
            return self.client._get("autonomy", "/assets/status", timeout_s=1.0)
        # END BATCH04 CAPABILITY HANDLERS
        if handler in {"wait", "semantic_noop"}:
            return {"ok": True, "skipped": True, "reason": handler}
        raise ValueError(f"unknown capability handler: {handler}")

    def _remember(self, name: str, ok: bool, reason: str, started: float) -> Dict[str, Any]:
        result = {
            "ok": bool(ok),
            "capability": name,
            "reason": reason,
            "latency_ms": round((time.monotonic() - started) * 1000.0, 2),
            "timestamp": time.time(),
        }
        self._last_result = dict(result)
        return result


__all__ = ["CapabilityExecutor"]
