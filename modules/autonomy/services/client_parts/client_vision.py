from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("autonomy.client")


class ClientVisionMixin:
    """Vision, VLM Bridge, Face tracking, and memory client methods."""

    urls: Dict[str, str]
    _post: Callable[..., Any]
    _get: Callable[..., Any]
    _async_post: Callable[..., Any]
    _async_get: Callable[..., Any]

    def _get_vlm(self, endpoint: str, params=None) -> Any:
        data = self._get("vlm", endpoint, params=params)
        if data is None:
            data = self._get("vision", endpoint, params=params)
        return data

    def get_latest_vision_results(self, limit: int = 5) -> List[Any]:
        data = self._get_vlm("/results/latest", params={"limit": limit})
        if not data:
            return []
        return data.get("results", [])

    def get_person_memory(self, person: str) -> Any:
        if not person:
            return None
        return self._get_vlm("/memory/person", params={"person": person})

    def list_people_memory(self) -> List[Any]:
        data = self._get_vlm("/memory/people")
        if not data:
            return []
        return data.get("people", [])

    def append_person_chat(self, person: str, text: str, role: str = "assistant") -> Any:
        if not person or not text:
            return None
        params = {
            "person": str(person),
            "text": str(text),
            "role": str(role or "assistant"),
        }
        return self._post("vlm", "/memory/chat", params=params)

    def start_face_follow(self, person: str | None = None) -> Any:
        params = {"person": str(person)} if person else None
        return self._post("vlm", "/follow/start", params=params)

    def stop_face_follow(self) -> Any:
        return self._post("vlm", "/follow/stop")

    def get_face_follow_status(self) -> Any:
        return self._get_vlm("/follow/status")

    def get_visual_context(self) -> Any:
        return self._get_vlm("/context/latest")

    def refresh_visual_context(self) -> Any:
        return self._post("vlm", "/context/refresh")

    def focus_person(self, person: str) -> Any:
        if not person:
            return None
        return self._post("vlm", "/focus/person", params={"person": str(person)})

    def start_owner_follow(self) -> Any:
        return self._post("vlm", "/follow/owner/start")

    async def async_focus_person(self, name: str) -> dict:
        if not name:
            return {"ok": False, "error": "name is empty"}
        return await self._async_post("vlm", "/focus/person", params={"person": str(name)})

    async def async_remember_person(
        self, name: str, relationship: str = "known", recognition_level: int = 2
    ) -> dict:
        return await self._async_post(
            "vlm", "/person/remember",
            json={
                "name": name,
                "relationship": relationship,
                "recognition_level": recognition_level,
            },
        )

    async def async_get_vision(self) -> dict:
        data = await self._async_get("vlm", "/context/latest", timeout=2.0)
        if data is None:
            data = await self._async_get("vision", "/context/latest", timeout=2.0)
        if isinstance(data, dict):
            if data.get("available"):
                ctx = data.get("context", {})
                return {
                    "available": True,
                    "people": ctx.get("people", []),
                    "objects": ctx.get("objects", []),
                    "hazards": ctx.get("hazards", []),
                    "scene_summary": ctx.get("summary", ""),
                    "importance": ctx.get("importance_score", 0.0),
                }
        return {"available": False, "people": [], "objects": [], "hazards": [], "scene_summary": "vision unavailable"}
