from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ExpressionOutputBridge:
    def __init__(self, engine: Any, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.engine = engine
        base = getattr(engine, "cfg", {}) if engine is not None else {}
        configured = base.get("output_bridge", {}) if isinstance(base, dict) and isinstance(base.get("output_bridge"), dict) else {}
        self.cfg = dict(configured)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self.enabled = bool(self.cfg.get("enabled", True))
        self.gateway_url = str(self.cfg.get("gateway_url") or "http://127.0.0.1:8080").rstrip("/")
        self.timeout_s = float(self.cfg.get("timeout_s", 0.8))
        self.endpoints = {
            "neopixel": "/neopixel/companion/mode",
            "oled_faces": "/oled_faces/event",
            "piservo": "/piservo/gesture",
        }
        custom = self.cfg.get("endpoints") if isinstance(self.cfg.get("endpoints"), dict) else {}
        self.endpoints.update({str(k): str(v) for k, v in custom.items()})
        self._last_apply: Dict[str, Any] = {"ok": True, "applied": False, "reason": "never_applied"}
        self._last_target_sig = ""

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "gateway_url": self.gateway_url,
            "endpoints": dict(self.endpoints),
            "last_apply": dict(self._last_apply),
        }

    def plan(self) -> Dict[str, Any]:
        payload = self.engine.get_state()
        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
        actions = self._actions(targets, state)
        return {"ok": True, "state": state, "targets": targets, "actions": actions}

    def apply(self, **_: Any) -> Dict[str, Any]:
        if not self.enabled:
            return self._remember(False, "bridge_disabled", [])
        plan = self.plan()
        sig = json.dumps(plan.get("targets") or {}, sort_keys=True, default=str)
        if sig == self._last_target_sig:
            return self._remember(True, "unchanged", [])
        self._last_target_sig = sig
        results: List[Dict[str, Any]] = []
        for action in plan["actions"]:
            results.append(self._send(action))
        ok = bool(results) and all(bool(result.get("ok")) for result in results)
        result = self._remember(ok, "applied" if ok else "output_failed", results)
        result["plan"] = plan
        return result

    def _actions(self, targets: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
        led = targets.get("led") if isinstance(targets.get("led"), dict) else {}
        oled = targets.get("oled") if isinstance(targets.get("oled"), dict) else {}
        pose = targets.get("pose") if isinstance(targets.get("pose"), dict) else {}
        return [
            {
                "component": "neopixel",
                "method": "POST",
                "path": self.endpoints["neopixel"],
                "payload": {"mode": self._led_mode(led.get("mode")), "eye_color": str(led.get("color") or "#4060ff")},
            },
            {
                "component": "oled_faces",
                "method": "POST",
                "path": self.endpoints["oled_faces"],
                "payload": {
                    "type": f"emotion:{str(oled.get('mood') or state.get('emotion') or 'neutral')}",
                    "data": {"attention": str(oled.get("attention") or state.get("attention") or "idle")},
                },
            },
            {
                "component": "piservo",
                "method": "POST",
                "path": self.endpoints["piservo"] + "?" + urlencode({"name": str(pose.get("ear_gesture") or "idle")}),
                "payload": None,
            },
        ]

    @staticmethod
    def _led_mode(value: Any) -> str:
        mode = str(value or "eye").strip().lower()
        if mode in {"off", "listen", "thinking", "eye", "wake_spin", "wake_chase"}:
            return mode
        return "eye"

    def _send(self, action: Dict[str, Any]) -> Dict[str, Any]:
        data = None
        headers: Dict[str, str] = {}
        if action.get("payload") is not None:
            data = json.dumps(action["payload"], ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.gateway_url + str(action["path"]),
            data=data,
            headers=headers,
            method=str(action.get("method") or "POST"),
        )
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body) if body else {}
                return {"ok": 200 <= int(response.status) < 300, "component": action["component"], "status": int(response.status), "response": parsed}
        except HTTPError as exc:
            return {"ok": False, "component": action["component"], "status": int(exc.code), "error": str(exc)}
        except (URLError, OSError) as exc:
            return {"ok": False, "component": action["component"], "error": str(exc)}

    def _remember(self, ok: bool, reason: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {
            "ok": bool(ok),
            "applied": bool(ok),
            "reason": reason,
            "results": results,
            "timestamp": time.time(),
        }
        self._last_apply = dict(result)
        return result


__all__ = ["ExpressionOutputBridge"]
