from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger("agent.tools.vision")


class VisionToolsMixin:
    """Vision and Perception tools for ToolRegistry."""

    def get_vision(self) -> str:
        if not self.client:
            return "Error: Vision client disconnected."
        results = self.client.get_latest_vision_results(limit=5)
        if not results:
            return "Vision results unavailable. Continue with text-only reasoning if needed."
        return f"Vision: {results}"

    def get_visual_context(self) -> str:
        """Return the latest cached visual context."""
        if not self.client:
            return "Error: Vision client disconnected."
        try:
            resp = self._http.get("vlm/context/latest", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("available"):
                    ctx = data.get("context", {})
                    parts = []
                    if ctx.get("summary"):
                        parts.append(f"Scene: {ctx['summary']}")
                    people = ctx.get("people", [])
                    if people:
                        names = [p.get("name", "Unknown") for p in people]
                        parts.append(f"People: {', '.join(names)}")
                    hazards = ctx.get("hazards", [])
                    if hazards:
                        parts.append(f"Hazards: {hazards}")
                    parts.append(f"Importance: {ctx.get('importance_score', 0.0)}")
                    return " | ".join(parts) if parts else "Scene is empty."
                refresh = self._http.post("vlm/context/refresh", timeout=8.0)
                if refresh.status_code == 200:
                    rdata = refresh.json()
                    rctx = rdata.get("context") or {}
                    if rctx:
                        summary = rctx.get("summary", "")
                        return (
                            f"Scene: {summary}"
                            if summary
                            else "Visual context refreshed."
                        )
                return "No visual context available yet. Camera may not be active."
            return "Vision context endpoint returned error."
        except Exception as exc:
            return f"Failed to get visual context: {exc}"

    def describe_scene(self) -> str:
        """Get a natural language scene description."""
        if not self.client:
            return "Error: Vision client disconnected."
        try:
            resp = self._http.get("vlm/context/latest", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                ctx = data.get("context", {})
                interpretation = ctx.get("persona_interpretation") or ctx.get("summary")
                if interpretation:
                    return interpretation
                return ctx.get("raw_vlm_observation", "No scene description available.")
            return "Scene description not available."
        except Exception as exc:
            return f"Failed to describe scene: {exc}"

    def remember_person(
        self, name: str, relationship: str = "known", recognition_level: int = 2
    ) -> str:
        """Save or update a person in memory."""
        try:
            resp = self._http.post(
                "vlm/person/remember",
                json_data={
                    "name": name,
                    "relationship": relationship,
                    "recognition_level": recognition_level,
                },
                timeout=2.0,
            )
            if resp.status_code == 200:
                return (
                    f"Remembered {name} as {relationship} (level {recognition_level})."
                )
            return f"Failed to remember person: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Failed to remember person: {exc}"

    def update_person_relationship(
        self, person_id: str, relationship: str = "", recognition_level: int = -1
    ) -> str:
        """Update a person's relationship or level."""
        try:
            resp = self._http.post(
                "vlm/person/relationship",
                json_data={
                    "person_id": person_id,
                    "relationship": relationship,
                    "recognition_level": recognition_level,
                },
                timeout=2.0,
            )
            if resp.status_code == 200:
                return f"Updated person {person_id}."
            return f"Failed to update person: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Failed to update person: {exc}"

    def ask_vlm_about_scene(self, question: str) -> str:
        """Ask the VLM a question about the current camera view."""
        try:
            resp = self._http.post(
                "vlm/ask",
                json_data={"question": question},
                timeout=max(2.0, float(self.vlm_ask_timeout_s)),
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("answer", "No answer from VLM.")
            return f"VLM question failed: HTTP {resp.status_code}"
        except Exception as exc:
            try:
                ctx_resp = self._http.get("vlm/context/latest", timeout=2.0)
                if ctx_resp.status_code == 200:
                    data = ctx_resp.json()
                    if data.get("available"):
                        ctx = data.get("context", {})
                        summary = (
                            str(ctx.get("summary", "")).strip()
                            or str(ctx.get("persona_interpretation", "")).strip()
                        )
                        if summary:
                            return f"Görüntü işleme gecikti; elimdeki son görüntüye göre {summary}"
            except Exception:
                pass
            return f"Görüntü işleme gecikti; elimdeki son görüntüye göre konuşuyorum. ({exc})"

    def focus_person(self, name: str) -> str:
        """Request the robot to focus on (look at) a specific person."""
        try:
            resp = self._http.post(
                "vlm/focus/person",
                json_data={"name": name},
                timeout=2.0,
            )
            if resp.status_code == 200:
                return f"Focusing on {name}."
            return f"Focus request failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Focus failed: {exc}"

    def start_owner_follow(self) -> str:
        """Start special owner-follow mode (higher priority than regular follow)."""
        try:
            resp = self._http.post("vlm/follow/owner/start", timeout=2.0)
            if resp.status_code == 200:
                return "Owner follow mode activated."
            return f"Owner follow failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Owner follow failed: {exc}"

    def stop_follow(self) -> str:
        """Stop any active follow mode."""
        try:
            resp = self._http.post("vlm/follow/stop", timeout=2.0)
            if resp.status_code == 200:
                return "Follow mode stopped."
            return f"Stop follow failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Stop follow failed: {exc}"
