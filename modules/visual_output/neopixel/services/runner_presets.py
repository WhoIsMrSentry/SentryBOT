from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Optional

import yaml

from modules.common.color_utils import parse_color as _common_parse_color

logger = logging.getLogger("neopixel.runner_presets")


def _strip_top_level_yaml_sections(text: str, keys: set[str]) -> str:
    """Remove specified top-level YAML sections while preserving comments and other keys."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        is_comment = stripped.startswith("#")
        is_blank = stripped.strip() == ""
        if indent == 0 and not is_comment and not is_blank:
            top_key = stripped.split(":", 1)[0].strip() if ":" in stripped else ""
            skipping = top_key in keys
        if not skipping:
            out.append(line)
    result = "".join(out)
    if result and not result.endswith("\n"):
        result += "\n"
    return result


class RunnerPresetsMixin:
    """Segment configuration and preset storage/loading management."""

    driver: Any
    _segments: dict[str, tuple[int, int]]
    _presets: dict[str, Any]
    _preset_store_path: Optional[Path]
    _preset_version: int
    _frame_lock: Any
    _preset_io_lock: threading.Lock

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
        io_lock = getattr(self, "_preset_io_lock", None)
        if io_lock is None:
            io_lock = threading.Lock()
            self._preset_io_lock = io_lock
        with io_lock:
            try:
                existing_text = ""
                if self._preset_store_path.exists():
                    existing_text = self._preset_store_path.read_text(encoding="utf-8")
                self._preset_version += 1
                preserved = _strip_top_level_yaml_sections(existing_text, {"presets", "presets_meta"})
                updated_block = yaml.safe_dump(
                    {
                        "presets": dict(self._presets),
                        "presets_meta": {"version": self._preset_version},
                    },
                    sort_keys=False,
                    allow_unicode=False,
                )
                content = (preserved + "\n" + updated_block) if preserved.strip() else updated_block
                self._preset_store_path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(self._preset_store_path.parent),
                    prefix=".presets_",
                    suffix=".yml.tmp",
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(content)
                    os.replace(tmp_name, self._preset_store_path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
                return True
            except Exception as exc:
                logger.warning("Failed to persist presets to %s: %s", self._preset_store_path, exc)
                return False

    def _segment_ranges(self, name: str | None) -> list[tuple[int, int]]:
        if not name:
            return []
        key = str(name).strip().lower()
        direct = self._segments.get(key)
        if direct is not None:
            return [direct]
        aliases = {
            "head": "jewel",
            "jewel": "head",
            "left_brow": "stick_left",
            "right_brow": "stick_right",
            "body": "stick",
            "brows": "stick",
            "eyebrows": "stick",
        }
        mapped = aliases.get(key, key)
        if mapped in self._segments:
            return [self._segments[mapped]]
        if mapped == "stick":
            ranges = [
                self._segments[seg]
                for seg in ("stick_left", "stick_right")
                if seg in self._segments
            ]
            if not ranges:
                ranges = [
                    bounds
                    for seg_key, bounds in sorted(self._segments.items())
                    if seg_key.startswith("stick_")
                ]
            if ranges:
                return ranges
            if "body" in self._segments:
                return [self._segments["body"]]
        return []

    def _segment_bounds(self, name: str | None) -> tuple[int, int] | None:
        ranges = self._segment_ranges(name)
        if not ranges:
            return None
        if len(ranges) == 1:
            return ranges[0]
        ordered = sorted(ranges)
        lo, hi = ordered[0]
        for s, e in ordered[1:]:
            if s <= hi:
                hi = max(hi, e)
            else:
                return (ordered[0][0], ordered[-1][1])
        return (lo, hi)

    @staticmethod
    def _parse_color(raw: Any) -> tuple[int, int, int] | None:
        return _common_parse_color(raw)

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
                ranges = self._segment_ranges(str(seg_name))
                if not ranges:
                    continue
                with self._frame_lock:
                    for start, end in ranges:
                        for idx in range(start, end):
                            self.driver.set(idx, *color)
                    self.driver.show()
        for effect, color, segment in animations:
            if hasattr(self, "animate"):
                self.animate(effect, color=color, segment=segment, coalesce=False)
        return True
