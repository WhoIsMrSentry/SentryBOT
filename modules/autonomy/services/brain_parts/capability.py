from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.capability")


class CapabilityHealthMixin:
    """Mixin for capability health checks, model asset statuses, and owner identification."""

    def _batch04_model_asset_status(self) -> dict:
        try:
            from modules.common.model_asset_truth import collect_asset_truth
            return collect_asset_truth(Path.cwd())
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_model_asset_status(self) -> dict:
        return self._batch04_model_asset_status()

    def _batch04_pi_runtime_status(self) -> dict:
        try:
            from modules.autonomy.services.pi_hardware_runtime import PiHardwareRuntime
            cfg = (
                self.config.get("pi_hardware_runtime", {})
                if isinstance(self.config.get("pi_hardware_runtime", {}), dict)
                else {}
            )
            return PiHardwareRuntime(cfg, client=self.client).status()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_pi_runtime_status(self) -> dict:
        return self._batch04_pi_runtime_status()

    def _batch04_owner_learning(self):
        from modules.autonomy.services.owner_person_learning import OwnerPersonLearning

        cfg = (
            self.config.get("owner_learning", {})
            if isinstance(self.config.get("owner_learning", {}), dict)
            else {}
        )
        cur = getattr(self, "_batch04_owner_learning", None)
        if cur is None:
            cur = OwnerPersonLearning(
                cfg,
                client=self.client,
                memory=getattr(self, "world_memory", None),
            )
            setattr(self, "_batch04_owner_learning", cur)
        return cur

    def get_owner_learning_status(self) -> dict:
        try:
            return self._batch04_owner_learning().status()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def learn_owner_person(self, payload: Optional[dict] = None) -> dict:
        try:
            return self._batch04_owner_learning().learn(payload or {})
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def identify_owner_person(self, payload: Optional[dict] = None) -> dict:
        try:
            result = self._batch04_owner_learning().identify(payload or {})
            self.state["owner_identification"] = result
            return result
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["owner_identification"] = result
            return result

    def get_capability_health_snapshot(self) -> dict:
        """Return a cached, fail-closed capability and hardware health snapshot."""
        from modules.autonomy.services.robot_capability_map import load_registry
        from modules.autonomy.services.robot_runtime_profile import status as runtime_profile_status

        companion_cfg = self.config.get("companion_goals", {}) if isinstance(self.config, dict) else {}
        autonomy_cfg = companion_cfg.get("autonomy_policy", {}) if isinstance(companion_cfg, dict) else {}
        health_cfg = autonomy_cfg.get("health", {}) if isinstance(autonomy_cfg, dict) else {}
        max_age_s = max(0.0, float(health_cfg.get("max_age_s", 0.0) or 0.0))
        now = time.time()
        cached = (
            self.state.get("_capability_health_snapshot", {})
            if isinstance(getattr(self, "state", None), dict)
            else {}
        )
        if isinstance(cached, dict) and now - float(cached.get("timestamp", 0.0) or 0.0) <= max_age_s:
            return dict(cached)

        runtime = runtime_profile_status()
        try:
            pi_runtime = (
                self.get_pi_runtime_status()
                if hasattr(self, "get_pi_runtime_status")
                else {"ok": False, "reason": "pi_runtime_unavailable"}
            )
        except Exception as exc:
            pi_runtime = {"ok": False, "reason": "pi_runtime_error", "error": str(exc)}

        registry = load_registry()
        items = registry.get("capabilities", {}) if isinstance(registry.get("capabilities", {}), dict) else {}
        capabilities = {
            str(name): {
                "available": bool(value.get("enabled", True)) if isinstance(value, dict) else True,
                "risk": str(value.get("risk", "")) if isinstance(value, dict) else "",
            }
            for name, value in items.items()
        }
        components = {
            "runtime_profile": {"ok": bool(runtime.get("ok", False)), "reason": runtime.get("reason")},
            "pi_hardware": {"ok": bool(pi_runtime.get("ok", False)), "reason": pi_runtime.get("reason")},
            "capability_registry": {"ok": bool(registry.get("ok", False)), "reason": registry.get("reason")},
        }
        required = [str(name) for name in health_cfg.get("required_components", []) if str(name)]
        unavailable = [name for name in required if not bool(components.get(name, {}).get("ok", False))]
        snapshot = {
            "ok": not unavailable,
            "available": not unavailable,
            "timestamp": now,
            "max_age_s": max_age_s,
            "components": components,
            "capabilities": capabilities,
            "unavailable_components": unavailable,
        }
        self.state["_capability_health_snapshot"] = snapshot
        return dict(snapshot)
