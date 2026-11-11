from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from modules.common.color_utils import clamp_rgb, normalize_color

Color = Tuple[int, int, int]

_PALETTE_CACHE_LOCK = threading.Lock()
_PALETTE_CACHE: Dict[str, Tuple[float, "EmotionPalette"]] = {}
_SHARED_STORES: Dict[str, "EmotionStore"] = {}


@dataclass
class ColorEntry:
    name: Optional[str]
    color: Color


def _parse_color(value) -> ColorEntry:
    # Accept [r,g,b], "#RRGGBB", named colors, or {name, hex | r/g/b}
    if isinstance(value, dict):
        nm = str(value["name"]) if "name" in value else None
        if "hex" in value and isinstance(value["hex"], str):
            parsed = normalize_color(value["hex"])
            if parsed is not None:
                return ColorEntry(nm, parsed)
        if all(k in value for k in ("r", "g", "b")):
            return ColorEntry(nm, clamp_rgb(value["r"], value["g"], value["b"]))
        raise ValueError(f"Unsupported color format: {value!r}")
    parsed = normalize_color(value)
    if parsed is not None:
        return ColorEntry(None, parsed)
    raise ValueError(f"Unsupported color format: {value!r}")


def _resolve_palette_name(emotion: str) -> Optional[str]:
    """Map an arbitrary emotion label onto a palette file name via the shared vocab.

    Lets callers pass canonical autonomy moods (``joy``/``tired``) or any alias
    (``happy``/``sleepy``) and still land on a real palette file.
    """
    try:
        from modules.common.emotion_vocab import get_vocab  # lazy: optional dep

        return get_vocab().render(emotion).palette
    except Exception:
        return None


@dataclass
class EmotionPalette:
    entries_by_emotion: Dict[str, List[ColorEntry]]

    def _lookup(self, emotion: str) -> Optional[List[ColorEntry]]:
        key = (emotion or "").lower()
        lst = self.entries_by_emotion.get(key)
        if lst:
            return lst
        palette_name = _resolve_palette_name(key)
        if palette_name and palette_name != key:
            return self.entries_by_emotion.get(palette_name)
        return None

    def random_color(self, emotion: str) -> Color:
        # Backward compatible simple color picker
        ent = self.random_entry(emotion)
        return ent.color

    def random_entry(self, emotion: str) -> ColorEntry:
        lst = self._lookup(emotion)
        if lst:
            return random.choice(lst)
        return ColorEntry("fallback", (255, 255, 255))

    def get_by_name(self, emotion: str, name: str) -> Optional[ColorEntry]:
        lst = self._lookup(emotion)
        if not lst:
            return None
        name = name.lower()
        for e in lst:
            if e.name and e.name.lower() == name:
                return e
        return None


class EmotionStore:
    """Caches colors loaded from YAML files located in a directory.

    Expected directory layout:
      emotions/
        admiration.yml
        joy.yml
        sadness.yml
        ...
    Each file may be either:
      - a list of colors ( [ [r,g,b], "#RRGGBB", ... ] )
      - or a mapping with key "colors": [...]
    """

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root = Path(root_dir or Path(__file__).parent).resolve()
        self._palette: Optional[EmotionPalette] = None

    @staticmethod
    def _dir_signature(root: Path) -> float:
        try:
            mtimes = [root.stat().st_mtime]
            mtimes.extend(p.stat().st_mtime for p in root.glob("*.yml"))
            return max(mtimes)
        except OSError:
            return 0.0

    def load(self, *, force_reload: bool = False) -> EmotionPalette:
        if self._palette is not None and not force_reload:
            return self._palette
        key = str(self.root)
        sig = self._dir_signature(self.root)
        if not force_reload:
            with _PALETTE_CACHE_LOCK:
                cached = _PALETTE_CACHE.get(key)
                if cached is not None and cached[0] == sig:
                    self._palette = cached[1]
                    return cached[1]

        colors: Dict[str, List[ColorEntry]] = {}
        for yml in sorted(self.root.glob("*.yml")):
            name = yml.stem.lower()
            try:
                with open(yml, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or []
                seq = data.get("colors", []) if isinstance(data, dict) else data
                parsed = []
                for item in seq:
                    try:
                        parsed.append(_parse_color(item))
                    except Exception:
                        continue
                if parsed:
                    colors[name] = parsed
            except Exception:
                continue
        palette = EmotionPalette(colors)
        with _PALETTE_CACHE_LOCK:
            _PALETTE_CACHE[key] = (sig, palette)
        self._palette = palette
        return palette

    def random_color(self, emotion: str) -> Color:
        return self.load().random_color(emotion)

    def random_entry(self, emotion: str) -> ColorEntry:
        return self.load().random_entry(emotion)

    def get_by_name(self, emotion: str, name: str) -> Optional[ColorEntry]:
        return self.load().get_by_name(emotion, name)


def get_shared_store(root_dir: str | Path | None = None) -> EmotionStore:
    """Return a shared, in-memory cached EmotionStore instance per directory."""
    resolved = str(Path(root_dir or Path(__file__).parent).resolve())
    with _PALETTE_CACHE_LOCK:
        store = _SHARED_STORES.get(resolved)
        if store is None:
            store = EmotionStore(resolved)
            _SHARED_STORES[resolved] = store
        return store
