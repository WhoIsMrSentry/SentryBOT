from __future__ import annotations
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import yaml


Color = Tuple[int, int, int]


@dataclass
class ColorEntry:
    name: Optional[str]
    color: Color


def _parse_color(value) -> ColorEntry:
    # Accept [r,g,b], "#RRGGBB", or {r,g,b}
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return ColorEntry(None, (int(value[0]), int(value[1]), int(value[2])))
    if isinstance(value, dict):
        # Named entry variants
        if "name" in value:
            nm = str(value.get("name"))
            if "hex" in value and isinstance(value["hex"], str):
                s = value["hex"]
                if s.startswith("#") and len(s) == 7:
                    r = int(s[1:3], 16); g = int(s[3:5], 16); b = int(s[5:7], 16)
                    return ColorEntry(nm, (r, g, b))
            if all(k in value for k in ("r", "g", "b")):
                return ColorEntry(nm, (int(value["r"]), int(value["g"]), int(value["b"])) )
        # Bare RGB mapping
        if all(k in value for k in ("r", "g", "b")):
            return ColorEntry(None, (int(value["r"]), int(value["g"]), int(value["b"])) )
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        r = int(value[1:3], 16); g = int(value[3:5], 16); b = int(value[5:7], 16)
        return ColorEntry(None, (r, g, b))
    raise ValueError(f"Unsupported color format: {value!r}")


@dataclass
class EmotionPalette:
    entries_by_emotion: Dict[str, List[ColorEntry]]

    def random_color(self, emotion: str) -> Color:
        # Backward compatible simple color picker
        ent = self.random_entry(emotion)
        return ent.color

    def random_entry(self, emotion: str) -> ColorEntry:
        lst = self.entries_by_emotion.get(emotion.lower())
        if lst:
            return random.choice(lst)
        return ColorEntry("fallback", (255, 255, 255))

    def get_by_name(self, emotion: str, name: str) -> Optional[ColorEntry]:
        lst = self.entries_by_emotion.get(emotion.lower())
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
        self.root = Path(root_dir or Path(__file__).parent)
        self._palette = None  # type: Optional[EmotionPalette]

    def load(self) -> EmotionPalette:
        if self._palette is not None:
            return self._palette
        colors: Dict[str, List[ColorEntry]] = {}
        for yml in sorted(self.root.glob("*.yml")):
            name = yml.stem.lower()
            try:
                with open(yml, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or []
                if isinstance(data, dict):
                    seq = data.get("colors", [])
                else:
                    seq = data
                parsed = []
                for item in seq:
                    try:
                        parsed.append(_parse_color(item))
                    except Exception:
                        continue
                if parsed:
                    colors[name] = parsed
            except Exception:
                # Skip malformed files
                continue
        self._palette = EmotionPalette(colors)
        return self._palette

    def random_color(self, emotion: str) -> Color:
        return self.load().random_color(emotion)

    def random_entry(self, emotion: str) -> ColorEntry:
        return self.load().random_entry(emotion)

    def get_by_name(self, emotion: str, name: str) -> Optional[ColorEntry]:
        return self.load().get_by_name(emotion, name)
