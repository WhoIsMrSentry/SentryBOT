"""Scene orchestration helpers for coordinated multi-modal behaviors."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger("autonomy.scenes")


class SceneMixin:
    """Runs small action timelines combining light/motion/speech."""

    def _get_scene_def(self, scene_name: str) -> Dict[str, Any] | None:
        scenes = self.config.get("scenes", {}) if isinstance(self.config, dict) else {}
        if not isinstance(scenes, dict):
            return None
        raw = scenes.get(scene_name)
        if isinstance(raw, dict):
            return raw
        return None

    def _run_scene(self, scene_name: str, context: Dict[str, Any] | None = None) -> bool:
        scene = self._get_scene_def(scene_name)
        if not scene:
            return False

        steps = scene.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return False

        ctx = dict(context or {})
        for step in steps:
            if not isinstance(step, dict):
                continue
            typ = str(step.get("type", "")).strip().lower()
            if not typ:
                continue
            try:
                self._run_scene_step(typ, step, ctx)
            except Exception as exc:  # pragma: no cover - best effort scene
                logger.debug("Scene step failed (%s): %s", typ, exc)
        return True

    def _run_scene_step(self, typ: str, step: Dict[str, Any], context: Dict[str, Any]) -> None:
        if typ == "event":
            event_type = str(step.get("name", "")).strip()
            if event_type:
                self.client.push_interaction_event(event_type, dict(context))
            return

        if typ == "effect":
            name = str(step.get("name", "COMET"))
            duration_ms = int(step.get("duration_ms", 700))
            force = bool(step.get("force", False))
            self.client.set_interaction_effect(name=name, duration_ms=duration_ms, force=force)
            return

        if typ == "effect_burst":
            name = str(step.get("name", "COMET"))
            duration_ms = int(step.get("duration_ms", 220))
            count = max(1, int(step.get("count", 2)))
            interval_ms = max(0, int(step.get("interval_ms", 80)))
            force = bool(step.get("force", False))
            for idx in range(count):
                self.client.set_interaction_effect(name=name, duration_ms=duration_ms, force=force)
                if idx < count - 1 and interval_ms > 0:
                    time.sleep(interval_ms / 1000.0)
            return

        if typ == "base":
            name = str(step.get("name", "BREATHE"))
            color = step.get("color")
            self.client.set_interaction_base(name=name, color=color)
            return

        if typ == "segment_fill":
            segment = str(step.get("segment", "")).strip()
            color = self._parse_color(step.get("color"))
            if segment and color:
                self.client.fill_neopixel_segment_color(segment, color[0], color[1], color[2])
            return

        if typ == "segment_anim":
            segment = str(step.get("segment", "")).strip()
            name = str(step.get("name", "PULSE")).strip()
            color = self._parse_color(step.get("color"))
            emotions = step.get("emotions")
            if isinstance(emotions, str):
                emotions = [emotions]
            iterations = step.get("iterations")
            if segment and name:
                self.client.set_neopixel_segment_effect(
                    segment=segment,
                    effect=name,
                    color=color,
                    emotions=emotions if isinstance(emotions, list) else None,
                    iterations=iterations,
                )
            return

        if typ == "preset":
            preset_name = str(step.get("name", "")).strip()
            if preset_name:
                self.client.apply_neopixel_preset(preset_name)
            return

        if typ == "anim":
            name = str(step.get("name", ""))
            if name:
                speed = float(step.get("speed", 1.0))
                loop = bool(step.get("loop", False))
                self._trigger_animation(name, speed=speed, loop=loop)
            return

        if typ == "head":
            pan = step.get("pan")
            tilt = step.get("tilt")
            if pan is None and tilt is None:
                return
            cur_pan = int(self.state.get("current_pan", 90))
            cur_tilt = int(self.state.get("current_tilt", 90))
            target_pan = max(0, min(180, int(float(pan)))) if pan is not None else cur_pan
            target_tilt = max(0, min(180, int(float(tilt)))) if tilt is not None else cur_tilt
            self.state["current_pan"] = target_pan
            self.state["current_tilt"] = target_tilt
            self.client.move_head(target_pan, target_tilt)
            return

        if typ == "speak":
            text_tmpl = str(step.get("text", "")).strip()
            if text_tmpl:
                text = self._render_scene_text(text_tmpl, context)
                emotion = step.get("emotion")
                if emotion is None:
                    self._speak_with_mood(text)
                else:
                    self._speak_with_mood(text, emotion=str(emotion))
            return

        if typ == "sleep":
            ms = int(step.get("duration_ms", 0))
            if ms > 0:
                time.sleep(ms / 1000.0)
            return

    @staticmethod
    def _render_scene_text(template: str, context: Dict[str, Any]) -> str:
        text = template
        for key, value in context.items():
            text = text.replace("{" + str(key) + "}", str(value))
        return text

    @staticmethod
    def _parse_color(raw: Any) -> tuple[int, int, int] | None:
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                return (int(raw[0]) & 255, int(raw[1]) & 255, int(raw[2]) & 255)
            except Exception:
                return None
        if isinstance(raw, str):
            s = raw.strip()
            if s.startswith("#") and len(s) >= 7:
                try:
                    v = int(s[1:7], 16)
                    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                except Exception:
                    return None
        return None
