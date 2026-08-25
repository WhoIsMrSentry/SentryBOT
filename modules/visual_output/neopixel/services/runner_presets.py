from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("neopixel.runner_presets")


class RunnerPresetsMixin:
    """Segment configuration and preset storage/loading management."""

    driver: Any
    _segments: dict[str, tuple[int, int]]
    _presets: dict[str, Any]
    _preset_store_path: Optional[Path]
    _preset_version: int
    _frame_lock: Any

    def _init_segments(self, segments: list[dict[str, Any]]) -> None:
        for item in segments:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if not name:
                continue
            start = int(item.get("start", 0))
            count = int(item.get("count", 0))
            if count <= 0:
                continue
            end = start + count
            start = max(0, min(self.driver.num_leds, start))
            end = max(start, min(self.driver.num_leds, end))
            if end > start:
                self._segments[name] = (start, end)

    def list_segments(self) -> list[dict[str, int | str]]:
        out = []
        for name, (start, end) in sorted(self._segments.items()):
            out.append({"name": name, "start": start, "count": end - start})
        return out

    def list_presets(self) -> list[str]:
        return sorted([str(k) for k in self._presets.keys()])

    def preset_version(self) -> int:
        return int(self._preset_version)

    def get_preset(self, name: str) -> dict[str, Any] | None:
        raw = self._presets.get(str(name))
        if isinstance(raw, dict):
            return dict(raw)
        return None

    def set_preset(self, name: str, spec: dict[str, Any], persist: bool = True) -> bool:
        key = str(name or "").strip()
        if not key or not isinstance(spec, dict):
            return False
        self._presets[key] = dict(spec)
        if persist:
            self._persist_presets()
        return True

    def delete_preset(self, name: str, persist: bool = True) -> bool:
        key = str(name or "").strip()
        if not key or key not in self._presets:
            return False
        del self._presets[key]
        if persist:
            self._persist_presets()
        return True

    def _persist_presets(self) -> bool:
        if self._preset_store_path is None:
            return False
        try:
            data: dict[str, Any] = {}
            if self._preset_store_path.exists():
                with open(self._preset_store_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                data = {}
            self._preset_version += 1
            meta = data.get("presets_meta") if isinstance(data.get("presets_meta"), dict) else {}
            meta["version"] = self._preset_version
            data["presets_meta"] = meta
            data["presets"] = dict(self._presets)
            self._preset_store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._preset_store_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=False)
            return True
        except Exception:
            return False

    def _segment_bounds(self, name: str | None) -> tuple[int, int] | None:
        if not name:
            return None
        key = str(name).strip().lower()
        bounds = self._segments.get(key)
        if bounds is not None:
            return bounds
        aliases = {"jewel": "head", "stick": "body", "head": "jewel", "body": "stick"}
        alt = aliases.get(key)
        if alt:
            return self._segments.get(alt)
        return None

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

    def apply_preset(self, name: str) -> bool:
        if hasattr(self, "companion_is_active") and self.companion_is_active():
            return False
        preset = self._presets.get(str(name))
        if not isinstance(preset, dict):
            return False
        if hasattr(self, "_cancel_animations"):
            self._cancel_animations()
        animations: list[tuple[str, tuple[int, int, int] | None, str]] = []
        for seg_name, spec in preset.items():
            if not isinstance(spec, dict):
                continue
            color = self._parse_color(spec.get("color"))
            effect = spec.get("effect")
            if isinstance(effect, str) and effect:
                animations.append((effect, color, str(seg_name)))
                continue
            if color is not None:
                bounds = self._segment_bounds(str(seg_name))
                if bounds is None:
                    continue
                start, end = bounds
                with self._frame_lock:
                    for idx in range(start, end):
                        self.driver.set(idx, *color)
                    self.driver.show()
        for effect, color, segment in animations:
            if hasattr(self, "animate"):
                self.animate(effect, color=color, segment=segment, coalesce=False)
        return True
