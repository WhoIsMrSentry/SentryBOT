from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.navigation")


class NavigationTopomapMixin:
    """Mixin for topomap navigation, safe places, and goal execution."""

    def _batch04_topomap_executor(self):
        from modules.autonomy.services.topomap_motion_executor import TopomapMotionExecutor

        cfg = (
            self.config.get("topomap_motion", {})
            if isinstance(self.config.get("topomap_motion", {}), dict)
            else {}
        )
        cur = getattr(self, "_batch04_topomap_motion", None)
        if cur is None:
            cur = TopomapMotionExecutor(cfg, client=self.client)
            setattr(self, "_batch04_topomap_motion", cur)
        return cur

    def get_navigation_topomap(self) -> dict:
        try:
            return self._batch04_topomap_executor().list_map()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def learn_navigation_topomap_place(self, payload: Optional[dict] = None) -> dict:
        try:
            result = self._batch04_topomap_executor().learn_place(payload or {})
            try:
                place = result.get("place") if isinstance(result, dict) else {}
                if isinstance(place, dict) and hasattr(self, "observe_world_memory"):
                    self.observe_world_memory(
                        {
                            "kind": "place",
                            "name": place.get("name") or place.get("id"),
                            "summary": place.get("summary") or "learned navigation place",
                            "confidence": place.get("safety_score", 0.6),
                            "salience": 0.7,
                            "tags": ["place", "topomap", str(place.get("kind") or "place")],
                            "details": place,
                        },
                        source="topomap_motion",
                    )
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def execute_navigation_goal(self, payload: Optional[dict] = None) -> dict:
        try:
            request = dict(payload or {})
            policy_name = str(request.pop("companion_policy", "") or "").strip()
            executor = self._batch04_topomap_executor()
            result = (
                executor.execute_companion_policy(policy_name, request)
                if policy_name
                else executor.execute_goal(request)
            )
            self.state["topomap_motion"] = result
            return result
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["topomap_motion"] = result
            return result

    def execute_safe_rest_corner(self, payload: Optional[dict] = None) -> dict:
        try:
            if not hasattr(self, "safe_navigation"):
                return {"ok": False, "available": False, "reason": "safe_navigation_missing"}
            result = self.safe_navigation.execute_rest_corner(payload or {})
            self.state["safe_navigation"] = result
            return result
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["safe_navigation"] = result
            return result

    def get_safe_navigation_status(self) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                return self.safe_navigation.status()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}

    def list_safe_places(self) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                return self.safe_navigation.list_places()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}

    def learn_safe_place(self, payload: Optional[dict] = None) -> dict:
        try:
            if hasattr(self, "safe_navigation"):
                result = self.safe_navigation.learn_place(payload or {})
                try:
                    place = result.get("place") if isinstance(result, dict) else {}
                    if isinstance(place, dict) and hasattr(self, "observe_world_memory"):
                        self.observe_world_memory(
                            {
                                "kind": "place",
                                "name": place.get("name") or place.get("id"),
                                "summary": place.get("summary") or "learned safe place",
                                "confidence": place.get("safety_score", 0.6),
                                "salience": 0.65,
                                "tags": ["safe_place", "rest_place"],
                                "details": place,
                            },
                            source="safe_navigation",
                        )
                except Exception:
                    pass
                return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "safe_navigation_missing"}
